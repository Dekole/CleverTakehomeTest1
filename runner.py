import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from checks import load_checks

LEADS_RENAME = {
    "lead_id": "l_leadid",
    "source": "l_source",
    "received_at": "l_receivedat",
    "first_name": "l_firstname",
    "last_name": "l_lastname",
    "phone": "l_phone",
    "email": "l_email",
    "consent_sms": "l_consentsms",
    "consent_call": "l_consentcall",
    "property_zip": "l_propertyzip",
    "lead_type": "l_leadtype",
    "status": "l_status",
}

OUTREACH_RENAME = {
    "attempt_id": "o_attempt_id",
    "lead_id": "o_lead_id",
    "channel": "o_channel",
    "attempted_at": "o_attempted_at",
    "status": "o_status",
    "agent_id": "o_agent_id",
}


# ── Data building ──────────────────────────────────────────────────────────────

def build_enriched(leads_df: pd.DataFrame, outreach_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join leads → outreach (one row per lead+attempt; leads with no
    attempts get one row with blank o_* columns). Adds five per-lead derived
    columns broadcast to every row for that lead.
    """
    lead_ids = set(leads_df["lead_id"])
    outreach_for_leads = outreach_df[outreach_df["lead_id"].isin(lead_ids)].copy()

    call_mask = outreach_for_leads["channel"] == "call"
    sms_mask = outreach_for_leads["channel"] == "sms"
    pickup_mask = call_mask & (outreach_for_leads["status"] == "completed")

    call_count = outreach_for_leads[call_mask].groupby("lead_id").size().rename("call_count")
    sms_count = outreach_for_leads[sms_mask].groupby("lead_id").size().rename("sms_count")
    pickup_count = outreach_for_leads[pickup_mask].groupby("lead_id").size().rename("pickup_count")
    first_attempt = outreach_for_leads.groupby("lead_id")["attempted_at"].min().rename("first_attempt_at")

    per_lead = (
        leads_df[["lead_id", "received_at"]]
        .merge(call_count.reset_index(), on="lead_id", how="left")
        .merge(sms_count.reset_index(), on="lead_id", how="left")
        .merge(pickup_count.reset_index(), on="lead_id", how="left")
        .merge(first_attempt.reset_index(), on="lead_id", how="left")
    )
    per_lead[["call_count", "sms_count", "pickup_count"]] = (
        per_lead[["call_count", "sms_count", "pickup_count"]].fillna(0).astype(int)
    )
    per_lead["status_pickup"] = per_lead["pickup_count"] > 0
    per_lead["lead_response_time"] = (
        (per_lead["first_attempt_at"] - per_lead["received_at"]).dt.total_seconds() / 60
    )

    derived_cols = per_lead[
        ["lead_id", "call_count", "sms_count", "pickup_count", "status_pickup", "lead_response_time"]
    ].rename(columns={"lead_id": "l_leadid"})

    leads_r = leads_df.rename(columns=LEADS_RENAME)
    outreach_r = outreach_for_leads.rename(columns=OUTREACH_RENAME)

    enriched = leads_r.merge(outreach_r, left_on="l_leadid", right_on="o_lead_id", how="left")
    enriched = enriched.merge(derived_cols, on="l_leadid", how="left")
    return enriched


def build_flag_columns(leads_df: pd.DataFrame, all_check_results: dict, check_modules: list) -> pd.DataFrame:
    """Build §3.4 aggregate flag columns — one row per lead."""
    category_map = {}
    for m in check_modules:
        ids = m.CHECK_ID if isinstance(m.CHECK_ID, list) else [m.CHECK_ID]
        cats = m.CATEGORY if isinstance(m.CATEGORY, list) else [m.CATEGORY]
        for cid, cat in zip(ids, cats):
            category_map[cid] = cat

    lead_ids = leads_df["lead_id"].tolist()
    err_legal: dict = {lid: [] for lid in lead_ids}
    err_others: dict = {lid: [] for lid in lead_ids}
    err_SLA: dict = {lid: False for lid in lead_ids}
    err_nooutreach: dict = {lid: False for lid in lead_ids}

    for check_id, df in all_check_results.items():
        if "lead_id" not in df.columns or df.empty:
            continue
        cat = category_map.get(check_id, "info")
        flagged = set(df["lead_id"].unique())
        for lid in flagged:
            if lid not in err_legal:
                continue
            if cat == "legal":
                err_legal[lid].append(check_id)
            elif cat == "sla":
                err_SLA[lid] = True
            elif cat == "nooutreach":
                err_nooutreach[lid] = True
            elif cat == "ops":
                err_others[lid].append(check_id)

    rows = []
    for lid in lead_ids:
        el = "|".join(err_legal[lid])
        eo = "|".join(err_others[lid])
        parts = (
            (["no_outreach"] if err_nooutreach[lid] else [])
            + err_legal[lid]
            + (["sla_breach"] if err_SLA[lid] else [])
            + err_others[lid]
        )
        rows.append({
            "lead_id": lid,
            "err_legal": el,
            "err_SLA": err_SLA[lid],
            "err_nooutreach": err_nooutreach[lid],
            "err_others": eo,
            "error": "|".join(parts),
        })
    return pd.DataFrame(rows)


def _clean(val):
    """Make a single value JSON-serializable."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if hasattr(val, "item"):          # numpy scalar
        return val.item()
    if hasattr(val, "strftime"):      # Timestamp / datetime
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    return val


def _serialize(df: pd.DataFrame) -> list:
    """Convert DataFrame to a list of JSON-serializable dicts."""
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _build_leads_records(enriched_df: pd.DataFrame, flag_df: pd.DataFrame) -> list:
    per_lead = (
        enriched_df
        .drop_duplicates("l_leadid")
        .merge(flag_df.rename(columns={"lead_id": "l_leadid"}), on="l_leadid", how="left")
    )

    cols = {
        "l_leadid": "lead_id",
        "l_source": "source",
        "l_receivedat": "received_at",
        "l_firstname": "first_name",
        "l_lastname": "last_name",
        "l_phone": "phone",
        "l_email": "email",
        "l_consentsms": "consent_sms",
        "l_consentcall": "consent_call",
        "l_propertyzip": "property_zip",
        "l_leadtype": "lead_type",
        "l_status": "lead_status",
        "lead_response_time": "lead_response_time",
        "status_pickup": "status_pickup",
        "call_count": "call_count",
        "sms_count": "sms_count",
        "pickup_count": "pickup_count",
        "err_legal": "err_legal",
        "err_SLA": "err_SLA",
        "err_nooutreach": "err_nooutreach",
        "err_others": "err_others",
        "error": "error",
    }
    out = per_lead[[c for c in cols if c in per_lead.columns]].rename(columns=cols)
    return _serialize(out)


def _build_outreach_records(enriched_df: pd.DataFrame) -> list:
    cols = {
        "l_leadid": "lead_id",
        "o_attempt_id": "attempt_id",
        "o_channel": "channel",
        "o_attempted_at": "attempted_at",
        "o_status": "status",
        "o_agent_id": "agent_id",
    }
    outreach = (
        enriched_df[enriched_df["o_attempt_id"].notna()]
        [[c for c in cols if c in enriched_df.columns]]
        .rename(columns=cols)
    )
    return _serialize(outreach)


# ── Check runner ───────────────────────────────────────────────────────────────

def _run_check(check_module, enriched_df, config, total_leads, checks_out_dir, run_at):
    """
    Run one check module. Returns (kpi_cards: list, results: dict {check_id: df}).
    Handles both single-CHECK_ID and list-CHECK_ID modules (e.g. called_multi).
    """
    if isinstance(check_module.CHECK_ID, list):
        check_ids = check_module.CHECK_ID
        labels = check_module.LABEL
        severities = check_module.SEVERITY
    else:
        check_ids = [check_module.CHECK_ID]
        labels = [check_module.LABEL]
        severities = [check_module.SEVERITY]

    raw = check_module.run(enriched_df, config)
    check_outputs = raw if isinstance(raw, dict) else {check_ids[0]: raw}

    cards = []
    results = {}
    for cid, label, severity in zip(check_ids, labels, severities):
        df = check_outputs.get(cid, pd.DataFrame())
        check_dir = checks_out_dir / cid
        check_dir.mkdir(parents=True, exist_ok=True)

        df_out = df.copy()
        df_out["run_at"] = run_at
        df_out.to_csv(check_dir / "latest.csv", index=False)

        count = int(df["lead_id"].nunique()) if ("lead_id" in df.columns and len(df) > 0) else 0
        pct = round(count / total_leads * 100, 1) if total_leads > 0 else 0.0

        cards.append({
            "check_id": cid,
            "label": label,
            "severity": severity,
            "count": count,
            "pct": pct,
            "run_at": run_at,
        })
        results[cid] = df

    return cards, results


# ── Pipeline entry point ───────────────────────────────────────────────────────

def run_pipeline(leads_path, outreach_path, out_dir, date_start=None, date_end=None, config=None):
    """
    Full pipeline: load → filter → enrich → run checks → build table data.
    Same code path used by both /process and the headless runner.
    """
    if config is None:
        config = {"SLA_MINUTES": int(os.environ.get("SLA_MINUTES", "60"))}

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    leads_df = pd.read_csv(leads_path)
    outreach_df = pd.read_csv(outreach_path)

    leads_df["received_at"] = pd.to_datetime(leads_df["received_at"])
    outreach_df["attempted_at"] = pd.to_datetime(outreach_df["attempted_at"])

    if date_start:
        leads_df = leads_df[leads_df["received_at"].dt.date >= pd.to_datetime(date_start).date()]
    if date_end:
        leads_df = leads_df[leads_df["received_at"].dt.date <= pd.to_datetime(date_end).date()]

    leads_df = leads_df.reset_index(drop=True)
    total_leads = len(leads_df)

    # Step 1: Build enriched file
    enriched_df = build_enriched(leads_df, outreach_df)
    enriched_df.to_csv(out_dir / "leads_outreach_enriched.csv", index=False)

    # Step 2: Run every check
    check_modules = load_checks()
    checks_out_dir = out_dir / "checks"
    kpi_cards = []
    all_check_results: dict = {}

    for check_module in check_modules:
        cards, results = _run_check(check_module, enriched_df, config, total_leads, checks_out_dir, run_at)
        kpi_cards.extend(cards)
        all_check_results.update(results)

    # Step 3 (archive/diff) — Phase 5
    # Step 4: Build §3.4 aggregate flag columns
    flag_df = build_flag_columns(leads_df, all_check_results, check_modules)

    # Build table data for the UI
    leads_records = _build_leads_records(enriched_df, flag_df)
    outreach_records = _build_outreach_records(enriched_df)
    check_lead_ids = {
        cid: df["lead_id"].unique().tolist()
        for cid, df in all_check_results.items()
        if "lead_id" in df.columns and not df.empty
    }
    check_severities = {c["check_id"]: c["severity"] for c in kpi_cards}

    return {
        "total_leads": total_leads,
        "kpi_cards": kpi_cards,
        "date_start": date_start,
        "date_end": date_end,
        "run_at": run_at,
        # Phase 3
        "leads_records": leads_records,
        "outreach_records": outreach_records,
        "check_lead_ids": check_lead_ids,
        "check_severities": check_severities,
    }
