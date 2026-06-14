import pandas as pd

CHECK_ID = "sla_breach"
LABEL = "SLA breach"
SEVERITY = "warn"
CATEGORY = "sla"
ORDER = 2
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "source", "received_at", "lead_response_time_minutes", "sla_minutes", "run_at"]


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Flag leads where time-to-first-contact exceeds SLA_MINUTES.
    Leads with no outreach are excluded (covered by no_outreach / unreachable).
    """
    sla_minutes = config.get("SLA_MINUTES", 60)

    per_lead = df.drop_duplicates("l_leadid")[
        ["l_leadid", "l_source", "l_receivedat", "lead_response_time"]
    ]

    flagged = per_lead[
        per_lead["lead_response_time"].notna()
        & (per_lead["lead_response_time"] > sla_minutes)
    ].copy()

    flagged["sla_minutes"] = sla_minutes

    return (
        flagged
        .rename(columns={
            "l_leadid": "lead_id",
            "l_source": "source",
            "l_receivedat": "received_at",
            "lead_response_time": "lead_response_time_minutes",
        })[["lead_id", "source", "received_at", "lead_response_time_minutes", "sla_minutes"]]
        .copy()
    )
