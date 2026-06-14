import pandas as pd

CHECK_ID = "clear"
LABEL = "Clear legal TCPA violations"
SEVERITY = "error"
CATEGORY = "legal"
ORDER = 4
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "attempt_id", "channel", "attempted_at", "consent_sms", "consent_call", "status", "run_at"]


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Flag each outreach row where contact was made on a channel the lead
    explicitly opted out of (consent == "FALSE").
    """
    sms_violation = (df["o_channel"] == "sms") & (df["l_consentsms"] == False)   # noqa: E712
    call_violation = (df["o_channel"] == "call") & (df["l_consentcall"] == False)  # noqa: E712

    return (
        df[sms_violation | call_violation]
        .rename(columns={
            "l_leadid": "lead_id",
            "o_attempt_id": "attempt_id",
            "o_channel": "channel",
            "o_attempted_at": "attempted_at",
            "l_consentsms": "consent_sms",
            "l_consentcall": "consent_call",
            "o_status": "status",
        })[["lead_id", "attempt_id", "channel", "attempted_at", "consent_sms", "consent_call", "status"]]
        .copy()
    )
