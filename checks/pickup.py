import pandas as pd

CHECK_ID = "has_pickup"
LABEL = "Leads with phone pickup"
SEVERITY = "info"
CATEGORY = "info"
ORDER = 9
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "call_count", "pickup_count", "run_at"]


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Flag leads where at least one call was answered (pickup_count > 0)."""
    per_lead = df.drop_duplicates("l_leadid")[
        ["l_leadid", "call_count", "pickup_count", "status_pickup"]
    ]

    return (
        per_lead[per_lead["status_pickup"]]
        .rename(columns={"l_leadid": "lead_id"})
        [["lead_id", "call_count", "pickup_count"]]
        .copy()
    )
