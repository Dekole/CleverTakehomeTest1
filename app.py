import os
import shutil
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from runner import run_pipeline

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "out"
WORKING_DIR = OUT_DIR / "working"


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", report=None, error=None)


@app.route("/process", methods=["POST"])
def process():
    WORKING_DIR.mkdir(parents=True, exist_ok=True)

    leads_file = request.files.get("leads_file")
    outreach_file = request.files.get("outreach_file")
    date_start = request.form.get("date_start", "").strip() or None
    date_end = request.form.get("date_end", "").strip() or None

    if leads_file and leads_file.filename:
        leads_path = WORKING_DIR / "leads.csv"
        leads_file.save(leads_path)
    else:
        leads_path = DATA_DIR / "leads.csv"

    if outreach_file and outreach_file.filename:
        outreach_path = WORKING_DIR / "outreach_log.csv"
        outreach_file.save(outreach_path)
    else:
        outreach_path = DATA_DIR / "outreach_log.csv"

    try:
        report = run_pipeline(
            leads_path=leads_path,
            outreach_path=outreach_path,
            out_dir=OUT_DIR,
            date_start=date_start,
            date_end=date_end,
        )
        return render_template("index.html", report=report, error=None)
    except Exception as exc:
        return render_template("index.html", report=None, error=str(exc))


@app.route("/reset", methods=["POST"])
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
