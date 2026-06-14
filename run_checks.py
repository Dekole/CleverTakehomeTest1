#!/usr/bin/env python3
"""
Headless runner — executes the full pipeline (§4 steps 1–5) without the web server.
Usage:
  python run_checks.py [--leads PATH] [--outreach PATH] [--date-start YYYY-MM-DD] [--date-end YYYY-MM-DD]
"""
import argparse
import sys
from pathlib import Path

from runner import run_pipeline

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR  = BASE_DIR / "out"


def main():
    parser = argparse.ArgumentParser(description="Run compliance checks headlessly.")
    parser.add_argument("--leads",      default=str(DATA_DIR / "leads.csv"),
                        help="Path to leads CSV (default: data/leads.csv)")
    parser.add_argument("--outreach",   default=str(DATA_DIR / "outreach_log.csv"),
                        help="Path to outreach log CSV (default: data/outreach_log.csv)")
    parser.add_argument("--date-start", default=None, metavar="YYYY-MM-DD",
                        help="Filter leads received on or after this date")
    parser.add_argument("--date-end",   default=None, metavar="YYYY-MM-DD",
                        help="Filter leads received on or before this date")
    args = parser.parse_args()

    leads_path    = Path(args.leads)
    outreach_path = Path(args.outreach)

    if not leads_path.exists():
        print(f"ERROR: leads file not found: {leads_path}", file=sys.stderr)
        sys.exit(1)
    if not outreach_path.exists():
        print(f"ERROR: outreach file not found: {outreach_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Running pipeline...")
    print(f"  leads:    {leads_path}")
    print(f"  outreach: {outreach_path}")
    if args.date_start or args.date_end:
        print(f"  range:    {args.date_start or '—'} → {args.date_end or '—'}")

    report = run_pipeline(
        leads_path=leads_path,
        outreach_path=outreach_path,
        out_dir=OUT_DIR,
        date_start=args.date_start,
        date_end=args.date_end,
    )

    print(f"\nRun at:      {report['run_at']}")
    print(f"Total leads: {report['total_leads']}\n")
    print(f"{'CHECK_ID':<22} {'SEV':<8} {'COUNT':>6}  {'PCT':>6}  {'NEW':>5}  {'RESOLVED':>9}")
    print("-" * 62)
    for card in report["kpi_cards"]:
        print(
            f"{card['check_id']:<22} {card['severity']:<8} {card['count']:>6}"
            f"  {card['pct']:>5.1f}%  {card['new_count']:>5}  {card['resolved_count']:>9}"
        )
    print()

    any_new = any(c["new_count"] > 0 for c in report["kpi_cards"])
    if any_new:
        print("New flags detected — see out/triggers.log")
    else:
        print("No new flags.")


if __name__ == "__main__":
    main()
