# Clever Lead Pipeline - Data Stats

## Basic counts

- leads.csv: 206 rows (excluding header)
- outreach_log.csv: 379 rows (excluding header)

## Leads with no outreach attempts

- 18 of 206 leads (8.74%) have zero rows in outreach_log.csv, meaning no call or SMS was ever attempted.
- All 18 of these leads share two things in common: source = "OfferNest" and status = "new" (lead_type split: 11 seller, 7 buyer).
- This points to a systemic gap with one partner source (OfferNest), not random drops, and is a strong candidate for "leads that never get touched."

## Suggested additional stats (not yet computed)

- Time-to-first-contact: distribution of (first outreach attempted_at - lead received_at) for leads that were contacted, to quantify how often the "minutes, not hours" SLA is missed.
- Duplicate/over-contact: leads contacted more than once on the same day or via both channels close together (the "contacted twice" complaint).
- Outreach outcome breakdown: distribution of outreach status (no_answer, delivered, completed, etc.) overall and by channel.
- Consent vs. contact mismatches: leads with consent_sms=FALSE that received an SMS, or consent_call=FALSE that received a call.
- No-outreach rate by source (beyond OfferNest) and by lead_type/property_zip, to see if the gap is isolated or broader.
- Lead status vs. outreach activity: do "new" status leads correlate with no outreach across all sources, or just OfferNest?

Let me know which of these you want added, or if you have other angles in mind.

## Analysis of leads_summary.csv (one row per lead)

### Response time
- 188 of 206 leads (91.3%) received at least one outreach attempt; 18 (8.7%, all OfferNest) never got one.
- Of the 188 contacted leads, median time to first attempt is 8 minutes, and 168 (89.4%) were first attempted within 15 minutes - the core dialer is generally fast when it fires.
- 13 leads (6.9% of contacted) waited 4-6 hours for first contact (256-361 min), and all 13 are from LeadBridge - a source-specific delay, not a general one. 7 more waited 1-4 hours.

### Leads with no successful connection
- 58 of 206 leads (28.2%) never had a successful connection, defined as no completed call and no delivered SMS. This breaks down as:
  - 18: never contacted at all (the OfferNest gap noted above).
  - 12: only contact attempt was an SMS that bounced because the number is a landline (status failed_err30006_landline), with no follow-up call - even though all 12 have consent_call=TRUE.
  - 27: a single call went unanswered (no_answer) with no SMS follow-up; 15 of those 27 have consent_sms=TRUE, so texting was an available fallback that wasn't used.
  - 1: voicemail left, no further attempt.

### Systemic issue: SMS-to-landline failures with no fallback
- 12 leads' only outreach attempt was an SMS that failed because the phone number is a landline. None of these 12 received a call instead, despite all 12 having consent_call=TRUE. Spread across HomeFlow (4), AgentMatch Pro (4), OfferNest (1), ListingLoop (1), SellFast Direct (1), LeadBridge (1) - this looks like a routing/sequencing bug (system should fall back to a call when SMS fails, or pick channel by number type up front), not a single partner's problem.
- These same 12 leads account for all 12 cases where firstresponse_type = "sms" (94% of contacted leads got a call first; these 12 are the only sms-first cases, and all 12 failed).

### Consent compliance
- 17 leads have consent_sms=FALSE; 4 received an SMS anyway (all delivered), spread across 4 different sources and agents (AgentMatch Pro, OfferNest, HomeFlow, LeadBridge) - no single root cause, but a TCPA-style compliance exposure worth a process/system check.
- All leads with consent_call=FALSE (0 in this dataset) - consent_call appears to be fully respected.

### Partner-source patterns
- OfferNest: 52 leads, 18 (35%) never contacted - the single largest "never touched" cluster, isolated to this source.
- LeadBridge: 45 leads, all contacted, but the only source with first-response times over 4 hours (13 of 45 leads, 29%).
- AgentMatch Pro, HomeFlow, ListingLoop, SellFast Direct: all leads contacted, median first response 7-10 min, no major outliers.

## Summary table (out of 206 leads, mutually exclusive, sums to 100%)

Each lead is counted in exactly one row below, ordered from most to least egregious outcome.

| Statistic                                                           | #       | %          | Outreach Success    | Notes                                                                                                                |
| ------------------------------------------------------------------- | ------- | ---------- | ------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Never contacted at all                                              | 18      | 8.7%       | No                  | All from OfferNest; consent_sms/consent_call both TRUE, so outreach was legally possible but never attempted         |
| Only attempt was SMS, and it failed (landline), no call fallback    | 12      | 5.8%       | No                  | consent_call=TRUE on all 12, so a call was a legal fallback option but never made                                    |
| Contacted late (>30 min to first attempt), but eventually connected | 20      | 9.7%       | Fail SLA            | All from LeadBridge; all 20 eventually got a completed call or delivered SMS, this is an SLA/timeliness failure only |
| Connected successfully, on time, consent honored                    | 124     | 60.2%      | Yes                 | The clean baseline: outreach worked as intended                                                                      |
| Call unanswered/voicemail, no SMS follow-up, SMS was consented      | 15      | 7.3%       | Unanswered, Bug Med | consent_sms=TRUE on all 15; texting was a legal follow-up option but never used                                      |
| Call unanswered/voicemail, no SMS follow-up, SMS not consented      | 13      | 6.3%       | Unanswered          | consent_sms=FALSE on all 13; no legal follow-up channel existed, so this is more "unlucky" than a process gap        |
| Connected successfully, but SMS sent despite consent_sms=FALSE      | 4       | 2.0%       | Bug High            | Compliance violation despite "successful" contact; spread across 4 sources, no single cause                          |
| **Total**                                                           | **206** | **100.0%** |                     |                                                                                                                      |

## Summary table v2 (revenue-weighted, out of 206 leads, sums to 100%)

$ column = % of leads x $24.3M, Clever Real Estate's estimated annual revenue per Growjo (~151 employees x ~$161K revenue/employee). Note: other sources show much lower estimates (e.g. $1-5M with 11-20 employees), so treat $24.3M as a directional/illustrative figure, not a verified number, and re-check before using externally.

"Successful Connection" below means the call itself was picked up (call_last_status = completed), regardless of how long it took; a delivered SMS alone does not count as connected, per your earlier question.

| Statistic                                                 | %          | $           | Outreach Success | Notes                                                      |
| --------------------------------------------------------- | ---------- | ----------- | ---------------- | ---------------------------------------------------------- |
| Never contacted at all                                    | 8.8%       | $2.14M      | No               | All OfferNest, zero outreach attempts                      |
| Only attempt was SMS, failed (landline), no call fallback | 5.8%       | $1.41M      | No               | consent_call=TRUE, never called                            |
| Successful Connection                                     | 42.2%      | $10.25M     | Yes              | Call picked up (87 leads, incl. 13 picked up >30 min late) |
| No Pickup                                                 | 43.2%      | $10.50M     | No               | Call ended in no_answer or voicemail (89 leads)            |
| **Total**                                                 | **100.0%** | **$24.30M** |                  |                                                            |

## Legal/consent violations (illegal_reachout.csv, % of 206 leads)

All flagged rows are SMS attempts; consent_call=TRUE for all 206 leads, so there are 0 call-consent violations.

Estimated annual exposure assumes a base of 150,000 leads/year and $1,000 per violation (e.g., clear violation $ = 1.9% x 150,000 x $1,000). $1,000/violation is an input assumption, not derived from the data.

| Category             | #      | % of leads | Est. annual violations (150K leads/yr) | Est. annual $ ($1,000/violation) | Notes                                                                                   |
| -------------------- | ------ | ---------- | ---------------------------------------- | ----------------------------------- | --------------------------------------------------------------------------------------- |
| Clear violation      | 4      | 1.9%       | 2,850 | $2,850,000 | consent_sms=FALSE but SMS sent anyway (and delivered)                                   |
| Borderline violation | 6      | 2.9%       | 4,350 | $4,350,000 | consent_sms blank/missing but SMS sent anyway (and delivered) - consent can't be proven |
| **Total flagged**    | **10** | **4.9%**   | **7,350** | **$7,350,000** | Now traced to one root cause: SMS fallback after an unanswered first call doesn't check consent_sms before sending |

## Other TCPA Legal Issues

- **Quiet Hour Violations**: 71 of 379 attempts (18.7%) across 51 distinct leads (54 calls, 17 SMS) occurred outside the allowable 8am-9pm window, including calls as early as 1am and as late as 11:51pm. Caveat: timestamps may be system time rather than the lead's local time zone, worth confirming, but as recorded this is real exposure under TCPA's calling-time rule.
- **Undocumented Consent (SMS)**: 17 of 206 leads (8.3%) have a blank consent_sms field (no record either way). 6 of these were texted anyway (already counted as borderline violations above); the other 11 represent the same missing-documentation gap, a TCPA record-keeping requirement, not just a contact-rules one.

## "You Contacted Me Twice" - Possible Sources

All leads in this dataset have at most 2 calls and at most 3 SMS attempts (no lead exceeds those totals). Breaking down the 76 leads (36.9% of 206) who were called more than once, plus SMS repeats:

| Category              | # Leads | % of 206 | Avg. gap between attempts | Notes                                                                                                                                                                                                                                                                                                                                 |
| --------------------- | ------- | -------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Called >1x, 0 pickups | 34      | 16.5%    | ~5.3 hrs                  | Both calls went unanswered. Customer never spoke to anyone but would see 2 missed-call notifications, plausible root cause of the complaint even with zero actual conversations.                                                                                                                                                      |
| Called >1x, 1 pickup  | 39      | 18.9%    | ~5.2 hrs                  | One call connected, the other didn't. Customer may remember an answered call plus a missed call as "you called twice."                                                                                                                                                                                                                |
| Called >1x, 2 pickups | 3       | 1.5%     | ~3.0 hrs                  | Customer answered both calls, hours apart. The least ambiguous case, an actual repeat conversation, but only 3 leads.                                                                                                                                                                                                                 |
| SMS >1x               | 12      | 5.8%     | n/a                       | Pushback: all 12 are retries of the same failing SMS to a landline (failed_err30006_landline x2-3). None were delivered, so the customer likely never received any text. This looks like a wasted-retry/system-inefficiency issue, not a "texted me twice" complaint, recommend tracking separately from the contact-frequency issue. |

**Takeaway**: the "0 pickups" and "1 pickup" groups (73 of 206 leads, 35.4%) are the most likely drivers of "you reached out 2 times" complaints, since both involve two separate dial attempts hours apart, regardless of whether either was answered. The "2 pickups" group is the cleanest evidence of an actual duplicate conversation but is rare (3 leads). The SMS-repeat group is likely a red herring for this specific complaint and probably belongs with the landline/no-fallback issue already noted above.
