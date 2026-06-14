import pandas as pd

CHECK_ID = ["called_multi_0", "called_multi_1", "called_multi_2"]
LABEL = ["Called >1x, 0 pickups", "Called >1x, 1 pickup", "Called >1x, 2 pickups"]
FLAG_LABEL = ["MULTI_DIAL·0", "MULTI_DIAL·1", "MULTI_DIAL·2"]
SEVERITY = ["info", "info", "concern"]
CATEGORY = ["info", "info", "info"]
ORDER = 10
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "call_count", "pickup_count", "run_at"]


def run(df: pd.DataFrame, config: dict) -> dict:
    """
    Three KPI cards from one file — leads called more than once, broken down
    by number of pickups (0, 1, or 2). Surfaces multi-dial patterns and their
    outcomes. Returns a dict keyed by CHECK_ID.
    """
    per_lead = (
        df.drop_duplicates("l_leadid")
        [["l_leadid", "call_count", "pickup_count"]]
        .rename(columns={"l_leadid": "lead_id"})
    )
    multi = per_lead[per_lead["call_count"] > 1]

    return {
        cid: multi[multi["pickup_count"] == n][["lead_id", "call_count", "pickup_count"]].copy()
        for n, cid in enumerate(CHECK_ID)
    }
