import pandas as pd

CHECK_ID = "borderline"
LABEL = "Borderline legal TCPA"
FLAG_LABEL = "TCPA_BORDERLINE"
SEVERITY = "warn"
CATEGORY = "legal"
ORDER = 5
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "attempt_id", "channel", "attempted_at", "consent_sms", "status", "run_at"]


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Flag each SMS row where consent_sms is blank/null — contact was attempted
    without provable consent (even a failed send counts as an attempt).
    """
    flagged = df[
        (df["o_channel"] == "sms") & df["l_consentsms"].isna()
    ]

    return (
        flagged
        .rename(columns={
            "l_leadid": "lead_id",
            "o_attempt_id": "attempt_id",
            "o_channel": "channel",
            "o_attempted_at": "attempted_at",
            "l_consentsms": "consent_sms",
            "o_status": "status",
        })[["lead_id", "attempt_id", "channel", "attempted_at", "consent_sms", "status"]]
        .copy()
    )
