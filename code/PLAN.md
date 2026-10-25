# Ghost Data Still Exists — Plan

## Context
Build a deletion-audit agent: for each of 518 cases decide COMPLETE / INCOMPLETE / NOT_APPLICABLE and emit ordered FINDING → REMEDIATION → VERIFICATION steps into root `output.csv`. Reported status and `system_activity` are claims; truth is in `dataset/evidence/` at `audit_at`.

Constraints (from user): Python via `..\.venv\Scripts\python.exe` (venv exists at `C:\Users\CASPER\Desktop\orchestrate\.venv`, `anthropic 2.2.0` already installed); model `claude-haiku-5-5`; key from `CLAIM_AGENT_ANTHROPIC_KEY` passed explicitly (`anthropic.Anthropic(api_key=...)`, never `ANTHROPIC_API_KEY`); LLM only for (a) deletion-intent classification of `request_text`, (b) extracting facts from PNG/PDF; everything else deterministic; LLM responses cached on disk keyed by hash of the full request; evaluation on the 32 samples (case, step, field, sequence accuracy). No code until approved. (Agent-trace note ignored per user.)

## What the data looks like (findings)
- Output order rule (verified on all 32 samples): phase, then operation order from the spec table, then `system_id`, `resource_id`. Findings: REMAINING_RECORD, EXPOSED_PII, ACTIVE_DATA_FLOW, RESTORE_RISK. Remediation: DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE, REDACT, ANONYMIZE. Verification: ABSENT, PRESENT, REDACTED, ANONYMIZED, FLOW_DISABLED, RESTORE_BLOCKED.
- Each INCOMPLETE/COMPLETE case has a "relevant resource set": account (always verified ABSENT, even if clean), security audit record (VERIFY_RECORD_PRESENT, keyed by `user_id`), plus search / support / analytics / export / marketing / integration / backup / tombstone / object records the user owns. Remediation exists only for resources found bad; verification covers every relevant resource with its required final state (rule table: search/export/profile → ABSENT, support msg → REDACTED, analytics → ANONYMIZED, security → PRESENT, flow → DISABLED, backup → RESTORE_BLOCKED, tombstone → REDACTED).
- Evidence cited = the latest file/snapshot with captured_at ≤ `audit_at` that shows the resource (e.g. audit 09-26T11:00 → evidence_94). Findings and COMPLETE verifications cite it; remediation and INCOMPLETE verification use `""`.
- Evidence families (12 parsers needed): `resource_lookup_trace` logs (key=value), `service_resource_export` JSON, `customer_data_inventory` SQL (9 tables + `snapshot_scope`), `customer_data_snapshot_bundle` JSON (per-snapshot `captured_at`), replica SQL (primary + replica tables, `record_json`, drift = row only in replica/stale), handover txt (pipe-delimited), notification/search diagnostic logs and export manifest JSON (`record_lookup` + FOUND/NOT_FOUND), noisy service logs in 5 syntaxes (service_events, structured JSON, syslog, application_trace, operations_stream, cloud_runtime), connector config JSON, small bespoke files 54–61 (+ 4 PDFs, 11 PNGs).
- NOT_APPLICABLE: `request_text` (many languages) + `CLASSIFY_REQUEST` activity rows ("classified … as non-deletion"). No samples exist; test set has ~10 per audit day.
- Identity: `user_identities` + `user_audit_log` give current/old emails, phones, hashes; match only on exact email (case-insensitive — handover has upper-case emails), sha256 hash, phone, `user_id`. Name-alike decoys (Mateo Rios vs Mateo Rios Gil) must not match.

## Resource-linking findings (added after deeper inspection)
Activity rows carry no identifiers (only resource ids); evidence rows for *absent* resources (404 / no hit) usually carry none either. Linking therefore uses, in priority order:
1. Direct identifier on an observation (email case-insensitive, hash, phone, `user_id`, `customer_reference`, `subject_reference`, `subject_selector`, `lookup_key`).
2. Transitive: same `resource_id` seen earlier (≤ audit_at, any file/snapshot, incl. inner snapshots of later-captured bundles) with an identifier, later seen absent/anonymized (e.g. account_5684 active as user_26 in the 09-09 snapshot, 404 in evidence_92).
3. Noisy logs (service_events, syslog, structured, trace, operations, cloud_runtime) are the email→resource link source for accounts: `profile_lookup_started lookup_key=<email>` + same `trace_id` `profile_lookup_completed resource_id=account_X rows=0` (evidence_93's case_09 account_3960 is only discoverable this way).
4. Cohort inference for still-unlinked resources: cases sharing the same `reported_at` day map to one activity batch; remove resources already linked to other users, then rank-order alignment (bundle store lists are in user order). Expected to be imperfect (e.g. account_3136, 3866, 5482, 6440 and analytics_5335/1895/4574/6077 in evidence_92 have no identifier anywhere); report this honestly in the evaluation report.

## USER AMENDMENTS (override anything above)
1. Remove cohort/rank-order linking (linking item 4 and hard case 1): list order is a generator artifact and a case-family shortcut. Resources not linkable by exact identity (direct id, transitive same-resource_id history, noisy-log lookups) are skipped; document as a known limitation in `evaluation_report.md`.
2. Intent decision comes from `request_text` via Haiku. `CLASSIFY_REQUEST` activity is only a claim: compare, report contradictions, never decide with it.
3. No `pdftotext`; PDFs via a Python library installed in the venv (pypdf; fall back to Haiku vision on rendered/scanned content).
4. LLM cache at repo-root `.cache/` (not `code/.cache`), added to `.gitignore`.
5. Custom evaluation cases are written inside `evaluation/evaluation_report.md` too (judge doesn't see .csv/.json).
6. Append all turns so far to `log.txt` per AGENTS.md §5.
7. Scope now: build end-to-end on the 32 samples only, run the evaluation, show results, STOP. The 518 run only after user approval.

## Hard cases (to be handled / likely losses)
1. **Anonymized analytics records have no identifier** (`user_id/email/hash = null`). Link to a COMPLETE user is not derivable from activity (policy-action rows are batched by time-of-day, order across users is shuffled — verified for cases 27/28). Only weak signal: in `customer_data_snapshot_bundle` the records of each store are listed in user order. Plan: rank-order heuristic across the day's cohort, validated on samples 21–28; accept it will be partly wrong on test data; document in evaluation report.
2. **Time filter:** a bundle file captured after `audit_at` still contains inner snapshots with earlier `captured_at` — filter per snapshot, not per file. Evidence after audit must never be cited.
3. **Stale vs latest state:** older snapshots show a record present that a later one (≤ audit) shows gone; use latest observation per resource ≤ audit_at. Replication drift: replica row present when primary lacks it ⇒ remaining record.
4. **Partially redacted records** (e.g. profile with only email left) still count as REMAINING_RECORD for USER_PROFILE; support message with email in text ⇒ EXPOSED_PII; `[REDACTED]` ⇒ clean.
5. **Tombstone:** `subject_reference` kept, name/email/phone/hash must be null; any non-null ⇒ EXPOSED_PII + REDACT.
6. **Active flows / restore:** `enabled=true` ⇒ ACTIVE_DATA_FLOW, remediation placed before deletions; `restore_allowed=true` ⇒ RESTORE_RISK. Backups are RETAINED (rule 14), never deleted; legal hold / security audit retained.
7. **Mixed reported statuses:** 254 COMPLETE reports; ~65% of those are really incomplete — never trust them.
8. **Images/PDFs:** only the few cases whose records appear only there need the LLM; text-extractable PDFs use `pdftotext` first (available at /mingw64/bin), PNGs go to Haiku vision. Must be validated against the sample cases that cite 55–61.
9. **Multi-language/ambiguous intent:** classify with Haiku (temperature 0, JSON out), plus deterministic cross-check with `CLASSIFY_REQUEST`.
10. Garbled non-ASCII text in my terminal output is just console encoding; all file I/O will be explicit UTF-8.

## Files and functions (all under `code/`)
- `main.py` — entry: `main()` → load data, run pipeline for each case, write root `output.csv` (sorted, UTF-8, `\n`); `--cases`, `--sample` flags.
- `ghost/config.py` — paths, model name, `get_client()` (reads `CLAIM_AGENT_ANTHROPIC_KEY`, passes `api_key=` explicitly).
- `ghost/data.py` — `load_requests`, `load_identities`, `load_audit_log`, `load_activity`, `load_rules`, `load_manifest`.
- `ghost/identity.py` — `build_identity_index()`, `resolve_subject(email, audit_at)` → `Subject(user_id, emails, phones, hashes)` using audit-log history, exact-match only.
- `ghost/evidence/` — `model.py` (`Observation(file_id, captured_at, system, resource_id, kind, fields, links)`), `loader.py` (`load_all_observations`), one parser per family: `sql_snapshots.py`, `json_bundles.py`, `json_exports.py`, `lookup_logs.py`, `noisy_logs.py`, `handover_txt.py`, `documents.py` (pdftotext + LLM), `images.py` (LLM).
- `ghost/llm.py` — `LLMCache` (SQLite/JSON files in `code/.cache/`, key = sha256 of full request payload incl. model, system prompt, messages, image bytes hash), `call_haiku()`, usage counters (calls, in/out tokens, cache hits) → feed `usage_report.md`.
- `ghost/intent.py` — `classify_intent(request_text)` (Haiku, cached) + `intent_for_case()` combining with `CLASSIFY_REQUEST`.
- `ghost/state.py` — `reconstruct_state(subject, audit_at, observations)` → per-resource latest state ≤ audit_at; `link_anonymous_records()` for hard case 1.
- `ghost/policy.py` — `evaluate_resource(state, rules)` → (finding op or None, remediation op, verification op); `decide_status()`.
- `ghost/plan.py` — `build_steps(case_findings)` → ordered, numbered steps; `SORT_KEYS` encode the phase/operation order; evidence_id rules.
- `evaluation/evaluate.py` — scores 32 samples: case accuracy, step-level (set match), field-level (per field), sequence accuracy; writes `evaluation/evaluation_report.md`. `evaluation/custom_cases.csv` + expected for ≥3 own cases incl. NOT_APPLICABLE (access/export/marketing opt-out, non-English).
- `evaluation/usage_report.md` — generated from `llm.py` counters on the final full run (Haiku calls, tokens, cost estimate).
- `README.md` update — setup with `..\.venv\Scripts\python.exe`, env var name, run commands.
- Logging: append per-turn entries to `log.txt` (AGENTS.md §5) once out of plan mode.

## Build order
1. Parsers + observation index; dump coverage stats per evidence file.
2. Identity + state + policy + plan on text-only evidence; run on samples, iterate until diff is minimal.
3. Add intent LLM and image/PDF LLM with cache.
4. Evaluate on samples, write custom cases, then full 518 run, `usage_report.md`.

## Verification
- `..\.venv\Scripts\python.exe code/evaluation/evaluate.py` → sample metrics; target 100% case accuracy on non-LLM-dependent samples.
- `..\.venv\Scripts\python.exe code/main.py` → `output.csv` has 518 rows, sorted, valid JSON, consecutive step_no, phase order, no evidence after `audit_at` cited (assert in code).
- Second run must be fully cache-hit (zero API calls) and byte-identical output.

## Open point for the user
Test-set evidence variety is large (12 families); I will prioritise families cited by the 32 samples first, then widen by checking all 518 cases produce non-empty plans. Anonymized-analytics linking (hard case 1) is the main accuracy risk.

---

# Current status (updated 2026-10-24)

## Done
- Deterministic pipeline in `code/ghost/` (identity, evidence parsers for logs/JSON/SQL/handover text, state at `audit_at`, policy, plan) and `code/pipeline.py`; `code/main.py --sample|--full`.
- Haiku (`claude-haiku-5-5`, key from `CLAIM_AGENT_ANTHROPIC_KEY`, passed explicitly) for deletion intent and PDF (`pypdf`) / PNG extraction; cache in repo-root `.cache/`, key = sha256 of the whole request payload.
- Sample evaluation (`code/evaluation/evaluate.py`): case accuracy 32/32, step precision 100%, step recall 85.5%, sequence 34.4% before the link-source work. All misses are resources without an exact identity link (see below).
- Full 518 run produced `output.csv` (156 COMPLETE, 352 INCOMPLETE, 10 NOT_APPLICABLE); 366 Haiku calls, 105,968 input / 23,592 output tokens; a second run is 100% cache hits and byte-identical.
- `CLASSIFY_REQUEST` comparison: 9 NOT_APPLICABLE cases without a linked claim, no contradictions otherwise (`.cache/classify_conflicts.txt`). The decision stays with `request_text`.
- `code/evaluation/validate_output.py` structural validator.
- Prices in `config.py`: 0.10 USD/Mtok input, 0.50 USD/Mtok output.

## Fixed since the safety-net commit
- Validator now OK on `output.csv` (see `code/evaluation/evaluation_report.md`, "Root-cause fixes"): citable-first state, alias join for console screenshots, request-time filter, improved media prompt.

## Decisions
- COMPLETE rows without an `account_service` verification (96 of 157): kept. The gold samples report COMPLETE in the same situation; what is missed is the verification step (a recall limitation, documented in the evaluation report), not the status.
- `evidence_60` (`marketing_001`): follow the catalog link (`activity_4008`, user_09). The person shown in the screenshot (Soo-jin Park) is in neither `user_identities.csv` nor `user_audit_log.csv`, so the image does not bind the record to another known subject.
- Evidence captured before `requested_at` is ignored for state: an observation made before the request cannot prove the state after deletion. It still counts for linking identifiers to resources.

## To do
All items from the earlier to-do list are done: missing-step audit (`code/evaluation/audit_missing.py`), validator fixes, derived end-to-end evaluation cases (`code/evaluation/derived_cases.py`), `README.md`, `code/evaluation/usage_report.md`, final `--full` run with `code/evaluation/validate_output.py`, `code.zip`.
Possible later work: recall of account verification steps is limited by identifiers the data does not contain (see the evaluation report).
