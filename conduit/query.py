from nostr_sdk import PublicKey
import pandas as pd
from conduit.config import WEAVIATE_PAGE_LIMIT
from conduit.log import logger
from conduit.utils import get_npub


def query_weaviate(client, npub=None, kind=None):
    where_clauses = []
    if npub:
        pk = PublicKey.from_bech32(npub).to_hex()
        npub_filter = {"path": ["pubkey"], "operator": "Equal", "valueString": pk}
        where_clauses.append(npub_filter)

    if kind:
        kind_filter = {"path": ["kind"], "operator": "Equal", "valueInt": int(kind)}
        where_clauses.append(kind_filter)

    combined_filter = None
    if where_clauses:
        if len(where_clauses) > 1:
            combined_filter = {"operator": "And", "operands": where_clauses}
        else:
            combined_filter = where_clauses[0]

    response = (
        client.query.get("Event", ["event_id, created_at, pubkey, kind, content"])
        # .get("Event", ["event_id, created_at, kind, content, _additional { vector }"])
        .with_where(combined_filter)
        .with_limit(WEAVIATE_PAGE_LIMIT)
        .do()
    )

    if "errors" in response:
        logger.error(f"Error querying weaviate: {response['errors'][0]['message']}")
    else:
        df = pd.DataFrame(response["data"]["Get"]["Event"])
        if "kind" in df.columns:
            df["kind"] = df["kind"].astype(str)
        return df


def search_weaviate(client, text, limit=None):
    if not limit:
        limit = 10
    response = (
        client.query.get("Event", ["event_id, created_at, pubkey, kind, content"])
        .with_near_text({"concepts": [text]})
        .with_limit(limit)
        .with_additional(["distance"])
        .do()
    )

    if "errors" in response:
        logger.error(f"Error querying weaviate: {response['errors'][0]['message']}")
    else:
        df = pd.DataFrame(response["data"]["Get"]["Event"])
        df["pubkey"] = df["pubkey"].apply(lambda x: PublicKey.from_hex(x).to_bech32())
        df["distance"] = df["_additional"].apply(
            lambda x: x["distance"] if isinstance(x, dict) else None
        )
        return df.sort_values("distance", ascending=True).drop(columns=["_additional"])


# todo: handle case where num users > 10k (WEAVIATE_PAGE_LIMIT)
# https://github.com/deepset-ai/haystack/issues/3390
def filter_users(client, min_num_events=5):
    where_filter = {
        "valueInt": min_num_events,
        "operator": "GreaterThanEqual",
        "path": ["hasCreated"],
    }

    response = (
        client.query.get(
            "User",
            [
                "pubkey",
                "hasCreated {... on Event { event_id, content _additional { vector } }}",
            ],
        )
        .with_where(where_filter)
        .with_limit(WEAVIATE_PAGE_LIMIT)
        .do()
    )

    data = []
    for user in response["data"]["Get"]["User"]:
        pubkey = user["pubkey"]
        if "hasCreated" in user:
            for event in user["hasCreated"]:
                event_id = event.get("event_id", "")
                content = event.get("content", "")
                vector = event.get("_additional", {}).get("vector", [])
                data.append(
                    {
                        "pubkey": pubkey,
                        "event_id": event_id,
                        "content": content,
                        "vector": vector,
                    }
                )
    df = pd.DataFrame(data)
    return df


def get_user_uuid(client, pubkey):
    user_response = (
        client.query.get("User", ["_additional { id }"])
        .with_where(
            {
                "operator": "Equal",
                "path": ["pubkey"],
                "valueString": pubkey,
            }
        )
        .do()
    )
    if user_response["data"]["Get"]["User"]:
        user_uuid = user_response["data"]["Get"]["User"][0]["_additional"]["id"]
    else:
        user_uuid = None
    return user_uuid


def get_similar_users(client, pubkey, limit=None):
    if not limit:
        limit = 5
    response = (
        client.query.get("User", ["pubkey, name"])
        .with_near_object({"id": get_user_uuid(client, pubkey)})
        .with_limit(limit + 1)
        .with_additional(["distance"])
        .do()
    )

    if "errors" in response:
        logger.error(f"Error querying weaviate: {response['errors'][0]['message']}")
    else:
        df = pd.DataFrame(response["data"]["Get"]["User"])
        df = df[df["pubkey"] != pubkey]
        df["distance"] = df["_additional"].apply(
            lambda x: x["distance"] if isinstance(x, dict) else None
        )
        df["npub"] = df["pubkey"].apply(get_npub)
        df = df.sort_values("distance", ascending=True).drop(columns=["_additional"])
        return df


def get_kind_counts(client):
    response = (
        client.query.aggregate("Event")
        .with_group_by_filter(["kind"])
        .with_fields("groupedBy { value }")
        .with_meta_count()
        .do()
    )
    events = response["data"]["Aggregate"]["Event"]
    kind_count_list = [
        {"kind": event["groupedBy"]["value"], "count": event["meta"]["count"]}
        for event in events
    ]

    df = pd.DataFrame(kind_count_list)
    return df
