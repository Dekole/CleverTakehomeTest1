# Lead Compliance &amp; Outreach Reconciliation — Build Spec

> Companion to `Linear Report.html`. Target: a working, Dockerized web app built with Claude Code in ~2 hours and deployed to an external URL. Audience for the tool: **Sales Ops / Data Analyst / Operations Manager**. Also designed to run **headless** (cron/daily) for ongoing monitoring with an auditable history — see §4 and §9.

---

## 1. What this tool does (one paragraph)

Upload (or use the bundled defaults) a **leads** file and an **outreach log** file, optionally filter by a received-at date range, click **Process**, and get a **compliance + reconciliation report**: a severity-coded summary of lead-handling issues (TCPA legal issues, SLA breaches, un-contacted-but-reachable leads, operational/data-quality gaps), a selectable leads table with drill-down detail, the outreach attempts tied to each lead, and two downloadable flatfiles (a joined leads+outreach file, and an "orphan" outreach file with no matching lead).

Two jobs, weighted equally:
1. **Compliance triage** — surface TCPA / SLA / operational risk fast, via a set of pluggable "checks."
2. **Reconciliation + export** — join leads to outreach and emit clean files.

The summary is built from a **`checks/` plugin directory**: each error/metric is one small Python file with a documented input, a documented output, and clear logic (§6). Adding a new analysis later means dropping a new file into `checks/` — no other code changes.

---

## 2. Inputs

| Input | Default | Notes |
|---|---|---|
| Leads file | `leads.csv` | optional upload; if not provided, backend uses the bundled default. To revert to the default after uploading, clear the file input (browser-native "remove file"). |
| Outreach log | `outreach_log.csv` | same as Leads file, above |
| Date start | (blank) | filters on `received_at`; blank = no lower bound |
| Date end | (blank) | filters on `received_at`; blank = no upper bound |
| **Process** button | — | runs the full pipeline (§4) and renders the report. Page loads with no report rendered — a report only appears after Process. |
| **Reset** button (not in mockup) | — | backend-only data reset, see §2.1 |

> Bundled defaults live at `data/leads.csv` and `data/outreach_log.csv` in the project root.

### 2.1 Reset button behavior

"Reset" is a **backend data reset**, not a UI/form reset:
- Clears all current/working state: any uploaded `leads.csv`/`outreach_log.csv`, the generated `leads_outreach_enriched.csv`, and every check's `latest.csv`.
- **Does not** touch `out/checks/<CHECK_ID>/archive/*` or `run_log.csv` — full run history is preserved for audit.
- Does **not** fall back to the bundled default files afterward — after Reset, the system has no current data at all, and the front end shows the empty/no-report state until the user selects files (default or custom) and clicks Process again.
- Suggested implementation: `POST /reset` deletes the working leads/outreach/enriched files and each check's `latest.csv`; leaves `archive/` and `run_log.csv` in place.

---

## 3. Data schemas

### 3.1 `leads.csv` (source columns)
`lead_id, source, received_at, first_name, last_name, phone, email, consent_sms, consent_call, property_zip, lead_type, status`

### 3.2 `outreach_log.csv` (source columns)
`attempt_id, lead_id, channel, attempted_at, status, agent_id`
- `channel` ∈ {call, sms}
- `status` ∈ {no_answer, completed, voicemail, delivered, failed_err30006_landline, …}

### 3.3 `leads_outreach_enriched.csv` — the canonical input to every check

Built once per run (step 1 of §4), this is **the single file every check in §6 reads**. It's a left join of leads → outreach (one row per lead+attempt; leads with zero attempts get one row with blank `o_*`), exactly like the existing `leads_outreach.csv`, **plus** five per-lead columns repeated on every row for that lead (computed once, centrally, so no check has to re-derive them):

| Column | Source | Type | Definition |
|---|---|---|---|
| `l_leadid` … `l_status` | `leads.csv` | — | all 12 columns from §3.1, `l_`-prefixed |
| `o_attempt_id` … `o_agent_id` | `outreach_log.csv` | — | all 6 columns from §3.2, `o_`-prefixed; blank if lead has no outreach |
| `call_count` | derived | int | count of `o_channel == "call"` rows for this lead |
| `sms_count` | derived | int | count of `o_channel == "sms"` rows for this lead |
| `pickup_count` | derived | int | count of `o_channel == "call" AND o_status == "completed"` rows for this lead |
| `status_pickup` | derived | bool | `pickup_count > 0` |
| `lead_response_time` | derived | minutes (float) | `min(o_attempted_at) − l_receivedat` for this lead; blank if no outreach |

Note: the existing `leads_outreach.csv`'s `error` column is **dropped** here — `error` is an *output* of the pipeline (§3.4), not an input.

### 3.4 Aggregated flag columns (built AFTER all checks run — see §4 step 4)

| Column | Type | Definition |
|---|---|---|
| `err_legal` | string | Pipe-joined list of `CHECK_ID`s from §6.4–6.7 (the `legal`-category checks) that fired for this lead, e.g. `"clear\|quiet_hour"`. Empty string if none. A lead can trigger more than one. |
| `err_SLA` | bool | True if `sla_breach` (§6.2) fired for this lead. |
| `err_others` | string | Pipe-joined list of `CHECK_ID`s from the `ops`-category checks (§6.3, §6.8) that fired. Empty string if none. |
| `err_nooutreach` | bool | True if `no_outreach` (§6.1) fired for this lead. |
| `error` | string | Export-only (§8.1). Union of every tag above for the lead, pipe-joined. |

---

## 4. Runner &amp; checks architecture

**Every run** (whether triggered by the Process button or a cron job) does the same six steps:

1. **Build the enriched file.** Load `leads.csv` + `outreach_log.csv`, apply the date filter, join, compute the five derived columns → write `leads_outreach_enriched.csv` (§3.3).
2. **Run every check.** Auto-discover `checks/*.py`. Each module exports:

   | Name | Type | Meaning |
   |---|---|---|
   | `CHECK_ID` | str | slug, e.g. `"clear"`, `"quiet_hour"`, `"called_multi_0"` |
   | `LABEL` | str | KPI card title |
   | `SEVERITY` | str | `error \| warn \| concern \| info` — drives KPI card color (§7.1) |
   | `CATEGORY` | str | `legal \| sla \| nooutreach \| ops \| info` — which §3.4 column the tag feeds |
   | `INPUT` | str | always `"leads_outreach_enriched.csv"` (documented per-check in §6 for clarity, but mechanically identical) |
   | `OUTPUT_COLUMNS` | list[str] | the columns this check writes — documented per-check in §6 |
   | `run(df, config) -> pd.DataFrame` | function | returns the rows (in `OUTPUT_COLUMNS` shape) that triggered this check — **not** just a boolean mask. Empty dataframe if nothing fired. |

3. **Archive + write, every time, no skipping.** For each check, regardless of whether the result changed:
   - write the result to `out/checks/<CHECK_ID>/archive/<run_timestamp>.csv`
   - diff this new result's `lead_id` set against the **previous** archive entry for this check → `new = current − previous` (newly flagged), `resolved = previous − current` (no longer flagged)
   - append `{run_at, total_leads, count_flagged, pct, new_count, resolved_count}` to `out/checks/<CHECK_ID>/run_log.csv`
   - overwrite `out/checks/<CHECK_ID>/latest.csv` with the new result
4. **Build §3.4 aggregate columns.** Read every check's `latest.csv`, group by `lead_id`, build `err_legal`/`err_others`/`err_SLA`/`err_nooutreach`/`error` per lead.
5. **(Headless mode only)** If any check's `new` set is non-empty, log to `out/triggers.log` — see §9.4 for the hook.
6. **Render** (web mode): KPI cards (one per check + "Total leads in range," in declared order) → leads table (joined `leads_outreach_enriched.csv` + step-4 flag columns) → detail panel → outreach table → exports (§8).

A new error report later = one new file in `checks/` implementing the §4 step-2 interface, reading `leads_outreach_enriched.csv`, writing its own `out/checks/<CHECK_ID>/`. No other code changes.

---

## 5. Checks — quick reference

| § | File | `CHECK_ID` | `CATEGORY` | `SEVERITY` | KPI card |
|---|---|---|---|---|---|
| — | *(not a check — computed in step 1)* | — | — | info | Total leads in range |
| 6.1 | `checks/no_outreach.py` | `no_outreach` | `nooutreach` | error | No contact — but reachable |
| 6.2 | `checks/sla_breach.py` | `sla_breach` | `sla` | warn | SLA breach |
| 6.3 | `checks/unreachable.py` | `no_contact_method` | `ops` | info | No contact — no method on file |
| 6.4 | `checks/consent_clear.py` | `clear` | `legal` | error | Clear legal TCPA violations |
| 6.5 | `checks/consent_borderline.py` | `borderline` | `legal` | warn | Borderline legal TCPA |
| 6.6 | `checks/consent_missing.py` | `consent_missing` | `legal` | concern | Consent missing / TCPA concern |
| 6.7 | `checks/quiet_hour.py` | `quiet_hour` | `legal` | error | TCPA quiet-hour violations |
| 6.8 | `checks/landline_no_fallback.py` | `landline_no_fallback` | `ops` | warn | SMS-to-landline, no call fallback |
| 6.9 | `checks/pickup.py` | `has_pickup` | `info` | info | Leads with phone pickup |
| 6.10 | `checks/called_multi.py` | `called_multi_0`, `_1`, `_2` | `info` | info | Called >1x, 0 / 1 / 2 pickups (3 KPI cards from one file) |

13 KPI cards total (1 "Total" + 12 from checks; §6.10 produces 3).

---

## 6. Check specs

Every check below has the same **Input**: `leads_outreach_enriched.csv` (§3.3). Only **Output** (schema) and **Logic** differ.

### 6.1 `checks/no_outreach.py` — `no_outreach`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/no_outreach/latest.csv` — columns: `lead_id, source, received_at, phone, email, consent_sms, consent_call, run_at`
- **Logic:** Group by `lead_id`. Flag if `call_count == 0 AND sms_count == 0` (zero outreach, from the precomputed columns) **and** the lead is reachable: (`l_phone` non-blank OR `l_email` non-blank) AND (`l_consentsms == TRUE` OR `l_consentcall == TRUE`). Reference: all 18 candidates in this dataset are OfferNest leads with both consents `TRUE`, so all 18 flag.

### 6.2 `checks/sla_breach.py` — `sla_breach`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/sla_breach/latest.csv` — columns: `lead_id, source, received_at, lead_response_time_minutes, sla_minutes, run_at`
- **Logic:** Flag if `lead_response_time > SLA_MINUTES` (config, default 60). Leads with zero outreach are excluded here (they're covered by 6.1/6.3 instead — `lead_response_time` is blank for them, so they can't be evaluated against a duration threshold). `SLA_MINUTES` is configurable; the resulting count will vary with the threshold, so no fixed reference number is given.

### 6.3 `checks/unreachable.py` — `no_contact_method`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/unreachable/latest.csv` — columns: `lead_id, source, phone, email, consent_sms, consent_call, run_at`
- **Logic:** Group by `lead_id`. Flag if `call_count == 0 AND sms_count == 0` (zero outreach) **and** ( (`l_phone` blank AND `l_email` blank) OR (`l_consentsms != TRUE` AND `l_consentcall != TRUE`) ) — i.e., not actionable, distinct from 6.1. Reference: expected to be **0 rows** in this dataset (every lead has `consent_call == TRUE`); included for completeness against future data.

### 6.4 `checks/consent_clear.py` — `clear`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/clear/latest.csv` — columns: `lead_id, attempt_id, channel, attempted_at, consent_sms, consent_call, status, run_at`
- **Logic:** Flag each outreach row where ( `o_channel == "sms"` AND `l_consentsms == "FALSE"` ) OR ( `o_channel == "call"` AND `l_consentcall == "FALSE"` ) — i.e., contact was made on a channel the lead explicitly opted out of. Reference: 4 rows in this dataset (all SMS; 0 call-consent violations since `consent_call == TRUE` for all 206 leads).

### 6.5 `checks/consent_borderline.py` — `borderline`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/borderline/latest.csv` — columns: `lead_id, attempt_id, channel, attempted_at, consent_sms, status, run_at`
- **Logic:** Flag each outreach row where `o_channel == "sms"` AND `l_consentsms` is blank/null AND the SMS was sent (any `o_status`, since even a failed send was still an attempted contact without provable consent). Reference: 6 rows in this dataset.

### 6.6 `checks/consent_missing.py` — `consent_missing`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/consent_missing/latest.csv` — columns: `lead_id, source, received_at, consent_sms, consent_call, run_at`
- **Logic:** Group by `lead_id`. Flag if `l_consentsms` is blank/null **and** the lead has zero `o_channel == "sms"` rows (the documentation gap exists but hasn't yet produced a 6.5 borderline contact). Reference: 11 leads in this dataset (17 total leads have blank `consent_sms`; 6 of those were texted and are counted in 6.5 instead — 6+11=17).

### 6.7 `checks/quiet_hour.py` — `quiet_hour`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/quiet_hour/latest.csv` — columns: `lead_id, attempt_id, channel, attempted_at, attempted_hour, run_at`
- **Logic:** Flag each outreach row where `hour(o_attempted_at) < 8` OR `hour(o_attempted_at) >= 21` (8am–9pm window, **system time as recorded** — no `property_zip`→timezone lookup; documented as an assumption in the UI). Reference: 71 rows across 51 distinct `lead_id`s in this dataset.

### 6.8 `checks/landline_no_fallback.py` — `landline_no_fallback`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/landline_no_fallback/latest.csv` — columns: `lead_id, source, sms_attempt_ids, sms_count, consent_call, run_at`
- **Logic:** Group by `lead_id`. Flag if every `o_channel == "sms"` row for the lead has `o_status == "failed_err30006_landline"`, **and** `call_count == 0`, **and** `l_consentcall == "TRUE"`. `sms_attempt_ids` = pipe-joined `o_attempt_id` values for that lead's SMS attempts. Reference: 12 leads in this dataset.

### 6.9 `checks/pickup.py` — `has_pickup`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** `out/checks/has_pickup/latest.csv` — columns: `lead_id, call_count, pickup_count, run_at`
- **Logic:** Group by `lead_id`. Flag if `status_pickup == TRUE` (i.e. `pickup_count > 0`). Info-only KPI, no flag tag on the lead.

### 6.10 `checks/called_multi.py` — `called_multi_0`, `called_multi_1`, `called_multi_2`
- **Input:** `leads_outreach_enriched.csv`
- **Output:** three files, same schema — `out/checks/called_multi_0/latest.csv`, `.../called_multi_1/latest.csv`, `.../called_multi_2/latest.csv`, columns: `lead_id, call_count, pickup_count, run_at`
- **Logic:** Group by `lead_id`. For N in {0, 1, 2}: flag if `call_count > 1 AND pickup_count == N`, write to that N's output file. Info-only KPIs. Reference: `called_multi_0` = 34 leads (16.5%), `called_multi_1` = 39 leads (18.9%), `called_multi_2` = 3 leads (1.5%).

---

## 7. UI

### 7.1 Severity → color (softened / accessible palette)
- **error** → muted red `#f4dcdc` bg / `#8c2b2b` text / `#c07070` border
- **warn** → muted amber `#f6e6cd` / `#8a5a1c` / `#cfa168`
- **concern** → muted yellow `#f3efcf` / `#6f6411` / `#c3b86a`
- **info** → neutral `#e9ebee` / `#3c434a` / `#aab2ba`
Always pair color with a text label/badge — never rely on color alone (accessibility).

### 7.2 Layout — Direction A (Linear report), per `Linear Report.html`
One scrolling page: Inputs → Summary cards (13 cards per §5) → Leads table → Lead detail → Outreach table → Exports.

- Leads table: `leads_outreach_enriched.csv` **grouped by `lead_id`** (one row per lead — drop `o_*` columns, keep `l_*` + the §3.3 derived columns + the §3.4 flag columns built in §4 step 4). Sortable + multi-selectable rows, flag-chip column (`err_legal` + `err_others`, plus `err_SLA`/`err_nooutreach` as their own chips), active-filter driven by KPI card selection (§7.3), Download. Free-text search = v2/nice-to-have (client-side filter) — not MVP.
- Lead detail panel: full row for the selected lead, with `err_nooutreach`, `err_legal`, `err_SLA`, `err_others` highlighted as "why this lead is flagged."
- Outreach table: `leads_outreach_enriched.csv` **at its native attempt grain**, filtered to the selected `lead_id`(s)' `o_*` columns only (rows with a blank `o_attempt_id` — i.e. leads with zero attempts — are excluded here, since they represent no outreach row, not an attempt). Selectable.
- Exports section (§8).
- Each KPI card shows its `run_at` timestamp (from that check's `run_log.csv`) — important once this runs headless, so the report visibly shows "as of [last run]."

> Note: with the §5/§6 checks (13 cards vs. the mockup's 11), the KPI grid will run longer than `Linear Report.html` shows — expected, the mockup predates the `called_multi_0` and `landline_no_fallback` additions.

> Note: the **Reset** button (§2.1) is not in `Linear Report.html`'s Inputs block — add it next to **Process**, styled as a secondary/non-primary `.btn`.

### 7.3 Interaction behaviors — KPI card click-to-filter

Exactly one KPI card is "active" at a time (radio-button behavior). Default active card on page load (post-Process) = **Total leads in range**.

- Clicking a check's card (any of the 12 cards from §6) sets it active and filters the leads table to leads where `lead_id` is in that check's `out/checks/<CHECK_ID>/latest.csv` (distinct `lead_id`s — for per-attempt checks like 6.4/6.5/6.7, this means "leads with at least one flagged attempt in this file").
- Clicking the currently-active check card again toggles it off, returning the active card to **Total leads in range** (table reverts to showing all leads, unfiltered).
- Clicking **Total leads in range** while a check card is active clears the filter (same effect as the toggle-off above).
- Clicking **Total leads in range** while it is already active is a no-op — it stays active.
- Visual: the active card carries a distinct highlighted/selected style (e.g., border + shadow); only one card has this style at a time.

---

## 8. Exports

### 8.1 Leads + Outreach flatfile — `leads_outreach_[datetime].csv`
`leads_outreach_enriched.csv` (§3.3) plus the `error` column (§3.4) appended per row. Columns:
```
l_leadid, l_source, l_receivedat, l_firstname, l_lastname, l_phone, l_email,
l_consentsms, l_consentcall, l_propertyzip, l_leadtype, l_status,
o_attempt_id, o_lead_id, o_channel, o_attempted_at, o_status, o_agent_id,
call_count, sms_count, pickup_count, status_pickup, lead_response_time, error
```
`error` = pipe-joined union of all fired check tags for the lead (§3.4).

### 8.2 Outreach with no matching leads — `outreach_nomatchingleads.csv`
All `outreach_log.csv` columns, for attempts whose `lead_id` does **not** exist in `leads.csv` (anti-join). Surfaces orphaned/mis-keyed outreach.

8.1 and 8.2 honor the active date range. Export scope (full filtered range vs. current selection) — see §10.4 (open).

### 8.3 Current leads source — `leads_[datetime].csv`
Raw pass-through of the currently active leads input (§3.1 columns, unchanged), exactly as loaded — whichever of `data/leads.csv` (default) or the most recently uploaded file is currently in effect. **Not** date-filtered — lets the user retrieve/verify exactly what's currently loaded.

### 8.4 Current outreach log source — `outreach_log_[datetime].csv`
Same as 8.3, for the currently active outreach log input (§3.2 columns, unchanged). Not date-filtered.

---

## 9. Suggested tech &amp; deploy (2-hour path), incl. headless mode

- **Backend:** Python + **Flask** + **pandas**. `checks/` is a plain directory of modules; load via `importlib` + `pkgutil.iter_modules`.
- **Frontend:** Flask + **Jinja** rendering `Linear Report.html`'s structure, with vanilla JS for row-select → detail and the v2 client-side search. No SPA build step.
- **Endpoints:** `POST /process` (multipart CSVs + date range → runs §4 pipeline, render report); `POST /reset` (backend data reset, §2.1); `GET /export/leads_outreach.csv`; `GET /export/nomatching.csv`.
- **Config:** `SLA_MINUTES` (default 60), quiet-hour window (default 8–21), via env vars or `config.py`.
- **Docker:** single `python:3.12-slim` image, `gunicorn -b 0.0.0.0:8000 app:app`. `EXPOSE 8000`.
- **9.4 Headless/cron mode:** `run_checks.py` executes §4 steps 1–5 with no web server — same code path the Process button uses, callable via cron. Step 5's trigger hook (`on_new_flags(check_id, new_lead_ids)`) is a stub that logs to `out/triggers.log` for v1; the contract exists so a webhook/email/Slack post can be wired in later without touching any check file. The web app (when running) reads `out/checks/*/latest.csv` + `run_log.csv` — it does not need to re-run checks on page load.
- **Acceptance:** load defaults → Process → all 13 KPI cards render with computed (not mockup) counts and a visible `run_at`; both exports download with correct headers and pipe-joined `error`; selecting a lead updates detail + outreach; orphan outreach appears only in `nomatchingleads`; running `run_checks.py` twice in a row produces two archive entries per check with `new_count = 0, resolved_count = 0`; dropping a new well-formed file into `checks/` produces a new KPI card without other code changes.

### 9.5 Public deployment hardening

All centralized — none of this touches individual `checks/*.py` files:

- **Auth:** HTTP Basic Auth via a single `before_request` hook in `app.py`, credentials from `AUTH_USER`/`AUTH_PASS` env vars. Gates every route.
- **Rate limiting:** Flask-Limiter, initialized once in `app.py`; `@limiter.limit("10/minute")` on `/process` and `/reset`.
- **Upload limits:** `MAX_CONTENT_LENGTH` (~5MB) in Flask config, plus one `validate_csv_columns()` helper (checked against §3.1/§3.2 schemas) called in `/process` before the pipeline runs — rejects bad uploads with a 400.
- **Archive retention:** in §4 step 3's shared archive-write loop, after appending the new entry, prune `out/checks/<CHECK_ID>/archive/` to the most recent `ARCHIVE_RETENTION` files (config, default 50). One change to the shared runner loop, applies to every check automatically.
- **Hosting:** prefer ephemeral storage (container restart wipes `out/` and any uploaded files) as a backstop.
- **Known limitation, accepted for v1:** `out/` is global/shared state — concurrent users overwrite each other's `latest.csv`/results. Fine for a demo; revisit if this becomes a real multi-user deployment.

---

## 10. Open questions / assumptions

1. **SLA threshold** — default 60 min, configurable. Does it differ by `lead_type` or `source`? (open)
2. **Quiet-hour timezone** — RESOLVED for v1: §6.7, system time as recorded, 8am–9pm, no zip lookup.
3. **"Reachable" definition for `no_outreach`** — §6.1's definition (phone or email + at least one consent flag TRUE). Confirm this is the right bar. (open)
4. **Export scope** — full filtered range vs. current selection. Spec assumes full filtered range. (open)
5. **`error` field format** — RESOLVED: pipe-joined list of all fired tags (§3.4, §8.1).
6. **(v2)** Free-text search — client-side filter only; confirm fields (lead_id, name, phone, email). Out of MVP scope.
7. **Checks ordering** — default = declaration order in §5. Fine for v1.
8. **Trigger action** — RESOLVED for v1: log-only to `out/triggers.log` (§9.4). Real notification channel is a later decision.

---

## 11. Annotation crosswalk (from the original wireframe)
- "color: red ERROR / orange warn / yellow concern / white info" → §7.1.
- "All data sourced from leads.csv EXCEPT … lead_response_time, status_pickup, err_*" → §3.3/§3.4.
- "Pretty table where user can select rows" → §7.2 (sortable + multi-select).
- "Leads Item Detail will show details of clicked item" → §7.2 detail panel.
- "Flatfile leads_outreach_[datetime].csv" + column list → §8.1.
- "outreach_nomatchingleads.csv, all columns from outreach_log.csv" → §8.2.
- "drop a new .py in checks/ to add an error report" → §4, §6.

---

## 12. Build phases (for incremental delivery)

Build in this order. Each phase should leave the app in a runnable, demoable state — checkpoint (commit/test) after each one before moving on.

**Phase 0 — Foundation**
- Build the `leads_outreach_enriched.csv` generator (§3.3) from `leads.csv` + `outreach_log.csv` (§3.1–3.2), with date-range filter (§2).
- Flask skeleton + `/process` endpoint (§9) using default files (§2).
- Render only the "Total leads in range" KPI card (§5, the *n/a* row).
- **Done when:** clicking Process with default files renders one KPI card with the correct count.

**Phase 1 — Legal checks**
- Implement the `checks/` plugin loader (§4 step 2) + the `legal`-category checks: §6.4 (`clear`), §6.5 (`borderline`), §6.6 (`consent_missing`), §6.7 (`quiet_hour`).
- Write each check's `latest.csv` (§4 step 3 — skip archive/diff for now, that's Phase 5).
- Render their 4 KPI cards with severity colors (§7.1).
- **Done when:** 5 cards total (Phase 0's + these 4) render with counts matching the reference numbers in §6.4–6.7.

**Phase 2 — Remaining checks**
- Add §6.1 (`no_outreach`), §6.2 (`sla_breach`), §6.3 (`unreachable`), §6.8 (`landline_no_fallback`), §6.9 (`has_pickup`), §6.10 (`called_multi_0/1/2`).
- **Done when:** all 13 KPI cards (§5) render with correct counts.

**Phase 3 — Interactive leads table**
- Leads table (lead-grain dedup), detail panel, outreach table (attempt-grain) — §7.2.
- KPI card click-to-filter (§7.3): single active filter, default = "Total leads in range," toggle-off behavior.
- Reset button (§2.1).
- **Done when:** clicking a card filters the table to the matching `lead_id`s; clicking a row populates the detail panel + outreach table; Reset clears working state and returns to the empty pre-Process view.

**Phase 4 — Exports + pre-deploy hardening**
- §8.1 `leads_outreach_[datetime].csv`, §8.2 `outreach_nomatchingleads.csv`, §8.3 `leads_[datetime].csv`, §8.4 `outreach_log_[datetime].csv`.
- Public deployment hardening, §9.5: Basic Auth (`before_request` hook), rate limiting on `/process` and `/reset`, `MAX_CONTENT_LENGTH` + `validate_csv_columns()` on upload. (The archive-retention item in §9.5 is deferred to Phase 5, since it has nothing to prune until archiving exists.)
- **Done when:** all four exports download correctly-shaped CSVs (8.1/8.2 honoring the active date range, 8.3/8.4 as unfiltered pass-throughs); the app requires Basic Auth credentials; oversized or malformed CSV uploads are rejected with a clear error; rapid repeated clicks on Process/Reset are throttled.

**Phase 5 — Audit / archive / headless (cut first if time-constrained)**
- Per-check `archive/<run_timestamp>.csv` + `run_log.csv` (§4 step 3), diff-based new/resolved tracking, `on_new_flags` hook.
- `run_checks.py` headless runner (§9.4).
- Archive retention from §9.5 (`ARCHIVE_RETENTION`, prune oldest entries).
- **Done when:** running `run_checks.py` twice produces two archive entries per check with `new_count = 0`, and archive directories don't grow past the retention cap.

**Phase 6 — Automation UI (placeholder / future)**
- UI section "2. Automation" added between Inputs and Summary with two disabled placeholder cards.
- **Email Alerts card:** text input for email address + "Save" button (disabled, opacity-60). Intended to send a summary email when `on_new_flags` fires (new flags detected since last run). Will be wired to the `on_new_flags` hook in `runner.py` in a future release. Badge: "Coming in v1.2".
- **Recurring Run card:** dropdown (Every day / Every Monday / Every weekday / Every Sunday) + "Schedule" button (disabled, opacity-60). Intended to configure a cron entry that calls `run_checks.py` on a schedule, allowing the app to run headlessly without manual intervention. Already supported by `run_checks.py` (§9.4) — only the scheduling UI and cron management are deferred.
- **Implementation path (when ready):**
  1. `on_new_flags(check_id, new_lead_ids, out_dir)` in `runner.py` — already implemented, currently logs to `out/triggers.log`. Extend to call an SMTP sender when `EMAIL_ALERT` env var is set.
  2. A `/save-alert-email` POST endpoint persists the email to `out/config.json`.
  3. Cron scheduling: a `/schedule` POST endpoint writes or replaces a crontab entry invoking `run_checks.py` at the chosen interval. Requires the container to run with cron access, or an external orchestration tool (e.g., GitHub Actions, DO scheduled functions).
- **Done when (Phase 6 complete):** Saving an email triggers a test email on the next flag detection; scheduling creates a verifiable cron entry; both actions are confirmed via a toast/status message in the UI.
