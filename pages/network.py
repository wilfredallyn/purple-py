import dash
from dash import html
from db import neo4j_driver
from nostr_sdk import PublicKey
import pandas as pd


dash.register_page(__name__, path_template="/network", name="Network")


def get_top_followed_pubkeys(tx, num_users=5):
    query = """
        MATCH (follower:User)-[:FOLLOWS]->(followed:User)
        RETURN followed.pubkey AS pubkey, COUNT(follower) AS followers_count
        ORDER BY followers_count DESC
        LIMIT $num_users
    """
    return tx.run(query, num_users=num_users).data()


def get_most_targeted_user(tx, num_users=5):
    query = f"""
        MATCH (targetedUser:User)<-[:TARGETS]-()
        RETURN targetedUser.pubkey AS pubkey, COUNT(*) AS times_targeted
        ORDER BY times_targeted DESC
        LIMIT {num_users}
    """
    return tx.run(query).data()


def get_most_active_users(tx, num_users=5):
    pass


def layout(num_followed=5, num_targeted=5):
    with neo4j_driver.session() as session:
        result_followed = session.read_transaction(
            get_top_followed_pubkeys, num_followed
        )
        result_targeted = session.read_transaction(get_most_targeted_user, num_targeted)

    df_followed = pd.DataFrame(result_followed)
    df_targeted = pd.DataFrame(result_targeted)

    if len(df_followed) == 0 or len(df_targeted) == 0:
        layout = html.Div(
            [
                html.P(f"Import data into Neo4j to analyze network"),
            ]
        )
        return layout

    if len(df_followed) > 0:
        df_followed["pubkey"] = df_followed["pubkey"].apply(
            lambda x: PublicKey.from_hex(x).to_bech32()
        )

    if len(df_targeted) > 0:
        df_targeted["pubkey"] = df_targeted["pubkey"].apply(
            lambda x: PublicKey.from_hex(x).to_bech32()
        )

    table_followed_data = [html.Tr([html.Th(col) for col in df_followed.columns])] + [
        html.Tr(
            [
                html.Td(
                    html.A(
                        df_followed.iloc[i]["pubkey"],
                        href=f"http://njump.me/{df_followed.iloc[i]['pubkey']}",
                    )
                )
                if col == "pubkey"
                else html.Td(df_followed.iloc[i][col])
                for col in df_followed.columns
            ]
        )
        for i in range(len(df_followed))
    ]

    table_targeted_data = [html.Tr([html.Th(col) for col in df_targeted.columns])] + [
        html.Tr(
            [
                html.Td(
                    html.A(
                        df_targeted.iloc[i]["pubkey"],
                        href=f"http://njump.me/{df_targeted.iloc[i]['pubkey']}",
                    )
                )
                if col == "pubkey"
                else html.Td(df_targeted.iloc[i][col])
                for col in df_targeted.columns
            ]
        )
        for i in range(len(df_targeted))
    ]

    layout = html.Div(
        [
            html.H3(f"Top {num_followed} Most Followed Pubkeys"),
            html.Table(table_followed_data),
            html.Hr(),  # Horizontal line to separate the sections
            html.H3(f"Top {num_targeted} Most Targeted Users"),
            html.Table(table_targeted_data),
        ]
    )

    return layout
