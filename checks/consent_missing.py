import pandas as pd

CHECK_ID = "consent_missing"
LABEL = "Consent missing / TCPA concern"
SEVERITY = "concern"
CATEGORY = "legal"
ORDER = 6
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "source", "received_at", "consent_sms", "consent_call", "run_at"]


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Flag leads where consent_sms is undocumented AND no SMS has been sent yet.
    Distinct from borderline (6.5): those leads were already texted without consent.
    This is the documentation gap that hasn't yet produced a violation.
    """
    per_lead = df.drop_duplicates("l_leadid")[
        ["l_leadid", "l_source", "l_receivedat", "l_consentsms", "l_consentcall", "sms_count"]
    ]

    flagged = per_lead[
        per_lead["l_consentsms"].isna() & (per_lead["sms_count"] == 0)
    ]

    return (
        flagged
        .rename(columns={
            "l_leadid": "lead_id",
            "l_source": "source",
            "l_receivedat": "received_at",
            "l_consentsms": "consent_sms",
            "l_consentcall": "consent_call",
        })[["lead_id", "source", "received_at", "consent_sms", "consent_call"]]
        .copy()
    )
