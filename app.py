import base64
import csv
import hashlib
import io
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from flask import Flask, Response, abort, redirect, render_template, request, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from checks import load_checks
from runner import build_flag_columns, run_pipeline

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "out"
WORKING_DIR = OUT_DIR / "working"
STATE_FILE = OUT_DIR / "pipeline_state.json"

# ── Rate limiting ──────────────────────────────────────────────────────────────
# Set RATE_LIMIT_ENABLED=true in .env to activate. Defaults to off.
_RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "false").lower() == "true"
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
    enabled=_RATE_LIMIT_ENABLED,
)

# ── Basic Auth ─────────────────────────────────────────────────────────────────
_AUTH_USER = os.environ.get("AUTH_USER")
_AUTH_PASS = os.environ.get("AUTH_PASS")


@app.before_request
def require_auth():
    if not _AUTH_USER or not _AUTH_PASS:
        return  # auth not configured — allow all (dev / no-creds deploy)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return _auth_challenge()
    try:
        user, _, password = base64.b64decode(auth[6:]).decode().partition(":")
    except Exception:
        return _auth_challenge()
    if user != _AUTH_USER or password != _AUTH_PASS:
        return _auth_challenge()


def _auth_challenge():
    return Response(
        "Unauthorized.",
        401,
        {"WWW-Authenticate": 'Basic realm="Lead Compliance Tool"'},
    )


# ── Upload validation ──────────────────────────────────────────────────────────
_LEADS_COLS = {
    "lead_id", "source", "received_at", "first_name", "last_name",
    "phone", "email", "consent_sms", "consent_call", "property_zip",
    "lead_type", "status",
}
_OUTREACH_COLS = {"attempt_id", "lead_id", "channel", "attempted_at", "status", "agent_id"}


def _validate_csv(file_storage, required_cols, label):
    """Read only the header row of an uploaded CSV and check required columns."""
    raw = file_storage.read()
    file_storage.seek(0)
    header = raw.split(b"\n")[0].decode("utf-8", errors="replace").strip()
    found = {c.strip() for c in header.split(",")}
    missing = required_cols - found
    if missing:
        raise ValueError(f"{label}: missing columns — {', '.join(sorted(missing))}")


# ── Visitor activity logging ───────────────────────────────────────────────────
def _unique_visitor_count() -> int:
    """Count distinct visitor_ids who have hit GET / — unique people who opened the app."""
    log_path = OUT_DIR / "site_activity.csv"
    if not log_path.exists():
        return 0
    try:
        with open(log_path, newline="") as f:
            reader = csv.DictReader(f)
            return len({r["visitor_id"] for r in reader if r.get("path") == "/" and r.get("method") == "GET"})
    except Exception:
        return 0



def _log_visit(username: str, status: int) -> None:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    ua = request.headers.get("User-Agent", "")
    visitor_id = hashlib.sha1(f"{ip}{ua}".encode()).hexdigest()[:8]
    row = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "username": username,
        "ip_address": ip,
        "visitor_id": visitor_id,
        "method": request.method,
        "path": request.path,
        "status": status,
        "user_agent": ua,
    }
    log_path = OUT_DIR / "site_activity.csv"
    write_header = not log_path.exists()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(row)


@app.after_request
def log_request(response):
    if response.status_code != 401:  # skip failed auth — don't log noise
        username = "anonymous"
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                username = base64.b64decode(auth[6:]).decode().split(":")[0]
            except Exception:
                pass
        _log_visit(username, response.status_code)
    return response


# ── Pipeline state ─────────────────────────────────────────────────────────────
def _save_state(date_start, date_end, leads_path, outreach_path):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "date_start": date_start,
        "date_end": date_end,
        "leads_path": str(leads_path),
        "outreach_path": str(outreach_path),
    }))


def _load_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text())


# ── Export helpers ─────────────────────────────────────────────────────────────
def _csv_response(df, filename):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _make_flag_df(enriched_df):
    """Reconstruct §3.4 flag columns from the on-disk latest.csv files."""
    check_modules = load_checks()
    check_results = {}
    for m in check_modules:
        ids = m.CHECK_ID if isinstance(m.CHECK_ID, list) else [m.CHECK_ID]
        for cid in ids:
            latest = OUT_DIR / "checks" / cid / "latest.csv"
            check_results[cid] = pd.read_csv(latest) if latest.exists() else pd.DataFrame()
    leads_df = (
        enriched_df[["l_leadid"]]
        .drop_duplicates()
        .rename(columns={"l_leadid": "lead_id"})
    )
    return build_flag_columns(leads_df, check_results, check_modules)


_EXPORT_COLS = [
    "l_leadid", "l_source", "l_receivedat", "l_firstname", "l_lastname",
    "l_phone", "l_email", "l_consentsms", "l_consentcall", "l_propertyzip",
    "l_leadtype", "l_status",
    "o_attempt_id", "o_lead_id", "o_channel", "o_attempted_at", "o_status", "o_agent_id",
    "call_count", "sms_count", "pickup_count", "status_pickup", "lead_response_time",
    "error",
]


# ── Template helpers ───────────────────────────────────────────────────────────
@app.context_processor
def inject_form_values():
    """Safely provide request.form values for template; returns empty on body errors."""
    try:
        return {
            "form_date_start": request.form.get("date_start", ""),
            "form_date_end": request.form.get("date_end", ""),
        }
    except Exception:
        return {"form_date_start": "", "form_date_end": ""}


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", report=None, error=None,
                           visitor_count=_unique_visitor_count())


@app.route("/process", methods=["POST"])
@limiter.limit("10/minute")
def process():
    WORKING_DIR.mkdir(parents=True, exist_ok=True)

    leads_file = request.files.get("leads_file")
    outreach_file = request.files.get("outreach_file")
    date_start = request.form.get("date_start", "").strip() or None
    date_end = request.form.get("date_end", "").strip() or None

    try:
        if leads_file and leads_file.filename:
            _validate_csv(leads_file, _LEADS_COLS, "Leads file")
            leads_path = WORKING_DIR / "leads.csv"
            leads_file.save(leads_path)
        else:
            leads_path = DATA_DIR / "leads.csv"

        if outreach_file and outreach_file.filename:
            _validate_csv(outreach_file, _OUTREACH_COLS, "Outreach file")
            outreach_path = WORKING_DIR / "outreach_log.csv"
            outreach_file.save(outreach_path)
        else:
            outreach_path = DATA_DIR / "outreach_log.csv"
    except ValueError as exc:
        return render_template("index.html", report=None, error=str(exc),
                               validation_error=True,
                               visitor_count=_unique_visitor_count())

    try:
        _save_state(date_start, date_end, leads_path, outreach_path)
        report = run_pipeline(
            leads_path=leads_path,
            outreach_path=outreach_path,
            out_dir=OUT_DIR,
            date_start=date_start,
            date_end=date_end,
        )
        return render_template("index.html", report=report, error=None,
                               visitor_count=_unique_visitor_count())
    except Exception as exc:
        return render_template("index.html", report=None, error=str(exc),
                               visitor_count=_unique_visitor_count())


@app.route("/reset", methods=["POST"])
@limiter.limit("10/minute")
def reset():
    if WORKING_DIR.exists():
        shutil.rmtree(WORKING_DIR)
    enriched = OUT_DIR / "leads_outreach_enriched.csv"
    if enriched.exists():
        enriched.unlink()
    checks_dir = OUT_DIR / "checks"
    if checks_dir.exists():
        for check_dir in checks_dir.iterdir():
            latest = check_dir / "latest.csv"
            if latest.exists():
                latest.unlink()
    return redirect(url_for("index"))


# ── §8.1 Leads + Outreach flatfile ────────────────────────────────────────────
@app.route("/export/leads_outreach")
def export_leads_outreach():
    enriched_path = OUT_DIR / "leads_outreach_enriched.csv"
    if not enriched_path.exists():
        abort(404, "No report generated yet — run Process first.")
    enriched_df = pd.read_csv(enriched_path)
    flag_df = _make_flag_df(enriched_df)
    result = enriched_df.merge(
        flag_df.rename(columns={"lead_id": "l_leadid"})[["l_leadid", "error"]],
        on="l_leadid", how="left",
    )
    result = result[[c for c in _EXPORT_COLS if c in result.columns]]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _csv_response(result, f"leads_outreach_{ts}.csv")


# ── §8.2 Outreach with no matching leads ──────────────────────────────────────
@app.route("/export/nomatching")
def export_nomatching():
    state = _load_state()
    if not state:
        abort(404, "No report generated yet — run Process first.")
    leads_path = Path(state["leads_path"])
    outreach_path = Path(state["outreach_path"])
    if not leads_path.exists() or not outreach_path.exists():
        abort(404, "Source files no longer available — run Process again.")
    leads_df = pd.read_csv(leads_path)
    outreach_df = pd.read_csv(outreach_path)
    orphan = outreach_df[~outreach_df["lead_id"].isin(leads_df["lead_id"])]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _csv_response(orphan, f"outreach_nomatchingleads_{ts}.csv")


# ── §8.3 Leads source file (unfiltered pass-through) ──────────────────────────
@app.route("/export/leads_source")
def export_leads_source():
    state = _load_state()
    if not state:
        abort(404, "No report generated yet — run Process first.")
    leads_path = Path(state["leads_path"])
    if not leads_path.exists():
        abort(404, "Source file no longer available — run Process again.")
    df = pd.read_csv(leads_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _csv_response(df, f"leads_{ts}.csv")


# ── §8.4 Outreach log source file (unfiltered pass-through) ───────────────────
@app.route("/export/outreach_source")
def export_outreach_source():
    state = _load_state()
    if not state:
        abort(404, "No report generated yet — run Process first.")
    outreach_path = Path(state["outreach_path"])
    if not outreach_path.exists():
        abort(404, "Source file no longer available — run Process again.")
    df = pd.read_csv(outreach_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _csv_response(df, f"outreach_log_{ts}.csv")


# ── Error handlers ─────────────────────────────────────────────────────────────
@app.errorhandler(413)
@app.errorhandler(RequestEntityTooLarge)
def file_too_large(_e):
    return render_template("index.html", report=None,
                           error="Upload too large — max 5 MB per file."), 413


@app.errorhandler(429)
def rate_limit_exceeded(_e):
    return render_template("index.html", report=None,
                           error="Too many requests — please wait a moment before trying again."), 429


if __name__ == "__main__":
    app.run(debug=True, port=5000)
