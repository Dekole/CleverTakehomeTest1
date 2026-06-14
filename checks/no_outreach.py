import pandas as pd

CHECK_ID = "no_outreach"
LABEL = "No contact — but reachable"
FLAG_LABEL = "NO_CONTACT"
SEVERITY = "error"
CATEGORY = "nooutreach"
ORDER = 1
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "source", "received_at", "phone", "email", "consent_sms", "consent_call", "run_at"]


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Flag leads with zero outreach attempts that are still reachable:
    (phone or email on file) AND (at least one consent is TRUE).
    Distinct from unreachable (6.3): those have no viable contact method.
    """
    per_lead = df.drop_duplicates("l_leadid")[
        ["l_leadid", "l_source", "l_receivedat", "l_phone", "l_email",
         "l_consentsms", "l_consentcall", "call_count", "sms_count"]
    ]

    no_outreach = (per_lead["call_count"] == 0) & (per_lead["sms_count"] == 0)
    has_contact_method = per_lead["l_phone"].notna() | per_lead["l_email"].notna()
    has_consent = (per_lead["l_consentsms"] == True) | (per_lead["l_consentcall"] == True)  # noqa: E712

    return (
        per_lead[no_outreach & has_contact_method & has_consent]
        .rename(columns={
            "l_leadid": "lead_id",
            "l_source": "source",
            "l_receivedat": "received_at",
            "l_phone": "phone",
            "l_email": "email",
            "l_consentsms": "consent_sms",
            "l_consentcall": "consent_call",
        })[["lead_id", "source", "received_at", "phone", "email", "consent_sms", "consent_call"]]
        .copy()
    )
