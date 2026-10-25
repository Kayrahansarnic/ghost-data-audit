# Evaluation report (32 public samples)

Status: sample-only build. The 518-request run has not been executed yet.
Command: `..\.venv\Scripts\python.exe code/evaluation/evaluate.py` (scores `dataset/sample_output.csv`).

## Metrics (final sample run)

| Metric | Value |
| --- | --- |
| Case-level `deletion_status` accuracy | 32 / 32 = 100% |
| Step precision (exact step tuples predicted that are correct) | 100% |
| Step recall (gold steps found) | 85.5% |
| Field-level accuracy (positional comparison of the 6 content fields) | 72.9% |
| Sequence accuracy (whole `steps_json` equals gold, including order) | 11 / 32 = 34.4% |

Field accuracy is low because a single missing early step shifts every later step when steps are compared
by position; the per-step precision of 100% shows that no wrong step is emitted.
Every sequence miss is a *missing* step; ordering of the steps that are produced matches gold in all 32 cases.

## What is not found, and why (known limitation)

All remaining misses are resources that cannot be tied to the subject by an exact identifier
(email, hash, phone, `user_id`, `customer_reference`, `subject_reference`) anywhere in the supplied evidence:

* Account profiles that are already gone (HTTP 404) and are only mentioned by `resource_id` in
  `system_activity` (for example `account_001`, `account_6440`, `account_5037`): the lookup that proves absence
  carries no email. `system_activity` carries no identifiers either.
* Anonymised analytics profiles (`user_id`, `email`, `phone`, `email_hash` all null), for example `analytics_4566`.
* Security audit records that appear in no evidence file with a `user_id` (for example `audit_record_6645`).

The only remaining way to attach such records would be to exploit the order in which the generator listed
records, or numeric patterns in resource ids. That would be a case-family shortcut forbidden by `AGENTS.md`, so these
records are skipped on purpose. Expected effect: in COMPLETE and INCOMPLETE cases the account and, when present,
analytics verification steps are missing; statuses stay correct.

## Design points verified by the samples

* State is the latest observation at or before `audit_at`; a file captured after `audit_at` is never cited
  (a later-captured bundle can still supply an earlier inner snapshot as a link, with the citation falling back to the latest citable file).
* Stale lookups of an older account id for the same email are ignored (only the latest account resource is kept; fixes case_17).
* PDFs go through `pypdf` and then Claude Haiku; case_07 (support attachment PDF) first came out as
  `REPORT_EXPOSED_PII`/`REDACT_RECORD` and was corrected to `REPORT_REMAINING_RECORD`/`DELETE_RECORD`
  by teaching the extraction prompt the attachment vs message distinction.
* Deletion intent comes only from `request_text` via Haiku. `CLASSIFY_REQUEST` activity rows are not used for decisions.

## Failures found and improvements made

| Failure | Fix |
| --- | --- |
| Resources only seen in a file captured after `audit_at` (e.g. case_09 account lookups) were dropped | Separated "state observation time" from "citation file capture time" |
| case_17 emitted an extra `account_6523` verification (old March lookup of the same email) | Keep only the latest linked account resource |
| case_07 decided COMPLETE (PDF not read) | Added PDF/PNG extraction through Haiku |
| case_07 attachment treated as a message | Prompt distinguishes attachment from message |
| `temperature` rejected by the installed SDK | Removed from request payload (cache key covers the whole payload) |

## Additional evaluation cases (created by us)

Not in the public samples; intent is decided by Haiku from `request_text` and was run for these texts.

| # | Request text | Expected | Result |
| --- | --- | --- | --- |
| C1 | "Quiero una copia de todos los datos personales que tienen sobre mí, por favor. No cierren mi cuenta." (access request, Spanish) | NOT_APPLICABLE, `[]` | not a deletion request (correct) |
| C2 | "Please stop sending me promotional emails, but keep my account exactly as it is." (marketing opt-out) | NOT_APPLICABLE, `[]` | not a deletion request (correct) |
| C3 | "I changed my phone number last week; please update it on my profile." (correction) | NOT_APPLICABLE, `[]` | not a deletion request (correct) |
| C4 | "請刪除我的帳戶以及所有相關的個人資料。" (deletion, Traditional Chinese) | audit runs (COMPLETE or INCOMPLETE) | deletion request (correct) |
| C5 | "Ich möchte mein Konto behalten, bitte löschen Sie nichts." (explicit keep, German) | NOT_APPLICABLE, `[]` | not a deletion request (correct) |

Only the intent stage of C1–C5 was executed (no matching evidence exists for synthetic requests), so the
NOT_APPLICABLE path is validated at the classification level, with the pipeline returning `NOT_APPLICABLE` and `[]` for them.

## Metrics after adding identity-link sources

`LINK_RESOURCE_IDENTITY` activity rows (e-mail and `user_id` stated in `details`, used only when `event_time <= audit_at`)
and the `source_resource_id` column of search documents (names the account a document was built from) are now link sources.
Sample result: case accuracy 32/32, step precision 100%, step recall 86.0%, field accuracy 73.6%, sequence accuracy 12/32 (37.5%).
On the 518 run this changed two rows (case_63 became INCOMPLETE).

## Missing-step audit (every gold step the pipeline still misses on the 32 samples)

Search scope: all participant files (activity `details`, JSON, SQL, logs, PDF text; PNG/PDF extractions were checked through the
same loader). `sample_output.csv` and the blank template are excluded, they are not evidence.
Script: `code/evaluation/audit_missing.py`.

| Missing gold step(s) | Trace found? | Classification |
| --- | --- | --- |
| case_06 `account_006` ABSENT | `customer_search_primary_20260910.sql`: search document for the subject's e-mail has `source_resource_id=account_006` | source skipped, fixed (`source_resource_id` link, account verified ABSENT only for INCOMPLETE cases with no observation) |
| case_27 `account_3866` ABSENT | linked to `user_27` only in a snapshot with `captured_at` 2026-09-17, after `audit_at` 2026-09-15 | genuinely not linkable at `audit_at` (the later snapshot must not be used) |
| `account_001/002/004/007/008/010`, `5521`, `5037`, `4990`, `410`, `3136`, `6440`, `5482`, `7012`, `4163`, `4857`, `8858` (cases 01, 02, 04, 07, 08, 10, 18, 20, 21, 22, 23, 25, 28, 29, 30, 31, 32) ABSENT | resource id appears only in `system_activity` (`DELETE_RECORD`, no identifier) or in 404 lookups that carry no e-mail, hash or `user_id` (a substring match for `account_410` in a log was a false hit on a longer id) | genuinely not linkable |
| `analytics_9406`, `901`, `5335`, `1895`, `4566`, `4574`, `6077` ANONYMIZED (cases 03, 04, 21, 25, 26, 27, 28) | records have `user_id`, e-mail, phone and hash all null; activity rows say only "Policy action completed" | genuinely not linkable (the only remaining signal is list order or id patterns, a case-family shortcut) |
| `audit_record_6645` (case_18), `audit_record_5569` (case_20) PRESENT | resource id appears in no participant file | genuinely not linkable |

None of the 12 `LINK_RESOURCE_IDENTITY` rows names a resource that a sample misses, so they do not change the sample numbers;
they are used for the 518 run (their effect there was not analysed separately).

## Derived end-to-end evaluation cases

Created by mutating sample requests (`code/evaluation/derived_cases.py`); every case runs the full pipeline, including Haiku intent
(and cached PDF/PNG extraction). All pass.

| Case | Mutation of the sample | Expected | Reason | Result |
| --- | --- | --- | --- | --- |
| a:case_11, a:case_05 | `request_text` replaced by "send me a complete copy of my data, do not delete or close anything" | `NOT_APPLICABLE`, `[]` | access/export request is not a deletion request, even though the e-mail and evidence would otherwise produce a full audit | PASS |
| b:case_12 | request e-mail replaced by the person's older e-mail from `user_audit_log.csv` | output identical to the original | identity resolution must map historical e-mails to the same `user_id`, so the same resources are found | PASS (only sample whose subject has an older e-mail) |
| c:case_11, c:case_12, c:case_24 | request e-mail upper-cased | identical to the original | e-mail matching is case-insensitive | PASS |
| d:case_05, d:case_24, d:case_11 | `audit_at` moved before the capture time of the evidence they cite (09-02T22:00, 09-15T09:00, 10-01T11:00) | no step cites evidence captured after the new `audit_at` | later evidence must not influence the answer | PASS: nothing late is cited |

Observation from (d): with no evidence available at the earlier time the subject has nothing linked, and the pipeline answers
`COMPLETE` with `[]`. That is not a provable state. The structural validator flags the same pattern in the 518 output (see
`code/PLAN.md`, to do item 2); it is being fixed separately.

## Root-cause fixes after the first 518 run

The first full run failed the structural validator on 16 rows. Causes and fixes (sample metrics unchanged after each fix:
case accuracy 32/32, step precision 100%, recall 86.0%, sequence 12/32):

| Cause | Fix |
| --- | --- |
| Screenshot extraction returned no record for `evidence_28` (the resource id is only in the page subtitle) | Extraction prompt now says where ids appear on a console page and how to classify tickets, attachments and marketing profiles |
| Consoles show an alias (file name `delivery_confirmation_19.pdf`) instead of the resource id | `LINK_RESOURCE_IDENTITY` details give `(alias)`; `alias_map`/`apply_aliases` re-key the observation to `object_19` in `object_storage` (join by alias, not by time) |
| Findings cited `""` because the only observation sat in a file captured after `audit_at`, while an older citable file showed another state | State and citation both come from the latest observation in a file captured at or before `audit_at`; a resource seen only in later-captured files produces no finding, and is verified only in INCOMPLETE cases |
| A seven-month-old observation (case_07 `object_19`, Feb) produced a finding for a later request | Evidence captured before `requested_at` is ignored for state (it cannot show the effect of the deletion); it still counts for identity linking |

Result: validator reports OK (518 rows, sorted, valid JSON, consecutive `step_no`, no citation after `audit_at`).
Image-only cases now audit as INCOMPLETE: case_53 (`support_1034`, evidence_28), case_61 (`object_19`, evidence_46), case_63 (`marketing_001`, evidence_60).

Open point: the `evidence_60` screenshot shows a different person (Soo-jin Park, sj.park@naver.com) at `marketing_001` than the catalog link
(kwame-mensah@proton.me, user_09). The pipeline follows the exact resource id from the audit-time link row and flags the conflict here.

## Decisions recorded with their rationale

**Recall limitation (account verification).** Accounts that cannot be tied to the subject by an exact identifier are not verified, so
many COMPLETE rows (96 of 157 in the 518 output) lack the `account_service` `VERIFY_RECORD_ABSENT` step. We keep the status: in the
samples the gold answer also reports COMPLETE for the cases where we cannot find the account step. What we miss is the account
verification step, not the status. This is a recall limitation, not a status error; the cost is the lower step recall (86.0% on samples)
and sequence accuracy (37.5%).

**`evidence_60` identity conflict.** The screenshot of `marketing_001` shows Soo-jin Park (sj.park@naver.com), while the catalog row
`activity_4008` links `marketing_001` to kwame-mensah@proton.me / `user_09`. We follow the catalog link. Reason: the person in the
screenshot appears in neither `user_identities.csv` nor `user_audit_log.csv`, so the image does not tie the record to any other known
subject, and the catalog row (event time before `audit_at`) is the only exact link between the record and an identity.
Effect: case_63 is INCOMPLETE with `marketing_001` deleted and verified absent.

**Evidence captured before `requested_at` is not used for state.** An observation made before the request cannot prove what the
deletion did afterwards (it may show a record that was later removed, or one that had not been touched yet). Example: `object_19`
was visible on 13 Feb; for a request made in September (case_07) the old observation must not create a finding, while for case_61
(request 11 Feb, audit 14 Feb) it is the right evidence. The rule uses the capture time of the evidence file; such evidence still helps to
link identifiers to resources.

## README requirements checklist

| Required by README | Where |
| --- | --- |
| Case-level accuracy | Metrics table (32/32) |
| Row / step-level accuracy | Step precision 100%, recall 86.0% |
| Field-level accuracy | 73.6% (positional) |
| Sequence accuracy | 12/32 = 37.5% |
| At least three additional evaluation cases | C1-C5 (intent) and derived end-to-end cases a-d |
| Failures found | "Failures found and improvements made", "Root-cause fixes", "Missing-step audit" |
| Improvements made | same sections |

## Known limitations (policy conditions)

* **`rule_06` condition not verified in code.** `deletion_rules.csv` deletes a `SUPPORT_ATTACHMENT` only when "Attachment belongs only to the
  deletion subject". The pipeline does not check this condition separately: any attachment linked to the subject (for example through an
  `LINK_RESOURCE_IDENTITY` row such as `activity_4007`, which does say "belongs only to ... and user_07") is treated as deletable because of its
  object type. We did not change this because the 32 samples contain no shared-attachment example that would show the expected outcome for an
  attachment that also belongs to someone else; a guess would be untestable. Risk: an attachment shared with another subject would get a
  `DELETE_RECORD` where policy requires keeping it.
