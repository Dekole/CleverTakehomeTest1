import pandas as pd

CHECK_ID = "no_contact_method"
LABEL = "No contact — no method on file"
SEVERITY = "info"
CATEGORY = "ops"
ORDER = 3
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "source", "phone", "email", "consent_sms", "consent_call", "run_at"]


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Flag leads with zero outreach AND no viable contact method:
    (no phone AND no email) OR (no consent on any channel).
    Distinct from no_outreach (6.1): those have a method but were never contacted.
    Expected to be 0 rows in this dataset — included for completeness.
    """
    per_lead = df.drop_duplicates("l_leadid")[
        ["l_leadid", "l_source", "l_phone", "l_email",
         "l_consentsms", "l_consentcall", "call_count", "sms_count"]
    ]

    no_outreach = (per_lead["call_count"] == 0) & (per_lead["sms_count"] == 0)
    no_contact_info = per_lead["l_phone"].isna() & per_lead["l_email"].isna()
    no_consent = (per_lead["l_consentsms"] != True) & (per_lead["l_consentcall"] != True)  # noqa: E712

    return (
        per_lead[no_outreach & (no_contact_info | no_consent)]
        .rename(columns={
            "l_leadid": "lead_id",
            "l_source": "source",
            "l_phone": "phone",
            "l_email": "email",
            "l_consentsms": "consent_sms",
            "l_consentcall": "consent_call",
        })[["lead_id", "source", "phone", "email", "consent_sms", "consent_call"]]
        .copy()
    )
