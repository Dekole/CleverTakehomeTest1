import pandas as pd

CHECK_ID = "quiet_hour"
LABEL = "TCPA quiet-hour violations"
FLAG_LABEL = "TCPA_QUIET_HRS"
SEVERITY = "error"
CATEGORY = "legal"
ORDER = 7
INPUT = "leads_outreach_enriched.csv"
OUTPUT_COLUMNS = ["lead_id", "attempt_id", "channel", "attempted_at", "attempted_hour", "run_at"]

# TCPA allowable window: 8am–9pm system time as recorded.
# No timezone lookup from property_zip — documented assumption.
QUIET_HOUR_START = 21  # 9pm
QUIET_HOUR_END = 8     # 8am


def run(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Flag each outreach row attempted before 8am or at/after 9pm.
    System time as recorded — no zip-to-timezone conversion.
    """
    hours = df["o_attempted_at"].dt.hour
    flagged = df[(hours < QUIET_HOUR_END) | (hours >= QUIET_HOUR_START)].copy()
    flagged["attempted_hour"] = hours[flagged.index]

    return (
        flagged
        .rename(columns={
            "l_leadid": "lead_id",
            "o_attempt_id": "attempt_id",
            "o_channel": "channel",
            "o_attempted_at": "attempted_at",
        })[["lead_id", "attempt_id", "channel", "attempted_at", "attempted_hour"]]
        .copy()
    )
