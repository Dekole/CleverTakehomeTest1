import pandas as pd

CHECK_ID = "landline_no_fallback"
LABEL = "SMS-to-landline, no call fallback"
FLAG_LABEL = "LANDLINE"
SEVERITY = "warn"
CATEGORY = "ops"
ORDER = 8
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "source", "sms_attempt_ids", "sms_count", "consent_call", "run_at"]


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Flag leads where every SMS attempt bounced as a landline error, no call
    was ever made, and a call was legally permissible (consent_call == TRUE).
    Points to a routing/sequencing bug: system should fall back to a call when
    SMS fails to a landline.
    """
    sms_rows = df[df["o_channel"] == "sms"][["l_leadid", "o_attempt_id", "o_status"]]

    if sms_rows.empty:
        return pd.DataFrame(columns=["lead_id", "source", "sms_attempt_ids", "sms_count", "consent_call"])

    sms_agg = (
        sms_rows
        .groupby("l_leadid")
        .agg(
            all_landline=("o_status", lambda x: (x == "failed_err30006_landline").all()),
            sms_attempt_ids=("o_attempt_id", lambda x: "|".join(x.astype(str))),
        )
        .reset_index()
    )
    all_landline_leads = sms_agg[sms_agg["all_landline"]][["l_leadid", "sms_attempt_ids"]]

    per_lead = df.drop_duplicates("l_leadid")[
        ["l_leadid", "l_source", "l_consentcall", "call_count", "sms_count"]
    ]

    merged = per_lead.merge(all_landline_leads, on="l_leadid", how="inner")
    flagged = merged[
        (merged["call_count"] == 0) & (merged["l_consentcall"] == True)  # noqa: E712
    ]

    return (
        flagged
        .rename(columns={
            "l_leadid": "lead_id",
            "l_source": "source",
            "l_consentcall": "consent_call",
        })[["lead_id", "source", "sms_attempt_ids", "sms_count", "consent_call"]]
        .copy()
    )
