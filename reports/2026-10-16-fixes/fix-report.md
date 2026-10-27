# Weaver understanding fixes — October 16, 2026

Automated suite: 145 passed. Live-model rerun: 28/28 passed all audit checks (baseline 21/28).

## What changed

- Enabled Nemotron reasoning to improve interpretation and actor attribution. Writing is saved immediately; background organization takes longer. Only structured final answers are parsed and stored.
- Clarified people versus personal tasks, completed actions, ongoing hobbies, business/location names, and reflective feelings.
- Restored typographic apostrophe variants to the exact source spelling in names and evidence. No paraphrase or expanded identity is accepted.
- Normalized exact matching existing facts as duplicates, preserving genuine corrections and distinct people.
- Added bounded corrective retries with specific feedback for obvious wrong-actor responses and dropped personal deadlines.
- Kept the original section/token/retry limits and atomic publication. No user entries were rewritten during this audit.

## Before and after — every original live case

| # | Case | Baseline | After fixes |
|---:|---|---|---|
| 1 | New name, short life update | Pass | Pass |
| 2 | Lowercase unfamiliar name | Pass | Pass |
| 3 | Lowercase name, errand without I | Pass | Pass |
| 4 | Apostrophe in a name | Needs attention | Pass |
| 5 | Accented name | Pass | Pass |
| 6 | Hyphenated name | Pass | Pass |
| 7 | Several new people | Pass | Pass |
| 8 | Known and new people in one entry | Needs attention | Pass |
| 9 | Correction of an existing birthday | Pass | Pass |
| 10 | Repeated fact | Needs attention | Pass |
| 11 | Personal task with no person | Pass | Pass |
| 12 | Everyday imperative | Pass | Pass |
| 13 | Vague personal reminder | Pass | Pass |
| 14 | Unnamed task after a named person | Pass | Pass |
| 15 | Relative deadline stays relative | Pass | Pass |
| 16 | Personal recurring goal | Pass | Pass |
| 17 | Promise involving a named person | Pass | Pass |
| 18 | Completed personal action | Pass | Pass |
| 19 | Negated completion | Pass | Pass |
| 20 | Uncertain completion | Pass | Pass |
| 21 | Future action is not a completion | Needs attention | Pass |
| 22 | Another person completed an action | Needs attention | Pass |
| 23 | Reflection without actionable details | Pass | Pass |
| 24 | Bare name does not create a profile | Pass | Pass |
| 25 | Business and place do not become people | Needs attention | Pass |
| 26 | Co-occurrence does not imply a relationship | Pass | Pass |
| 27 | One-off wish is a plan, not a hobby | Needs attention | Pass |
| 28 | Long entry preserves details across sections | Pass | Pass |

## Interpretation and limits

The final status combines the most recent full 28-case run with focused rechecks of cases 6, 9, 15, and 21 after narrow category/reference fixes. Each result records its verification run. It is not a claim that every intermediate run passed. These are fictional inputs run through the configured live provider. This is an observed rerun, not a guarantee of perfect accuracy on all journal writing. The baseline and final runs use the same expectations. Intermediate trials are retained in this folder rather than replacing the baseline.

## New regression coverage

- `test_apostrophe_variant_uses_exact_source_name[D\u2019Arcy-D'Arcy]`
- `test_apostrophe_variant_uses_exact_source_name[O'Neil-O\u2019Neil]`
- `test_typographic_quote_is_restored_to_exact_source_without_rewriting_words`
- `test_apostrophe_matching_does_not_expand_or_change_identity`
- `test_exact_duplicate_is_not_a_correction_or_assigned_to_another_person`
- `test_real_correction_is_not_normalized_into_a_duplicate`
- `test_explicit_birthday_correction_gets_its_single_known_predecessor`
- `test_ongoing_study_is_background_not_a_future_activity[interest]`
- `test_ongoing_study_is_background_not_a_future_activity[plan]`
- `test_administrative_task_stays_a_task_even_with_timing[Submit the form by Friday]`
- `test_administrative_task_stays_a_task_even_with_timing[Pay the rent tomorrow]`
- `test_administrative_task_stays_a_task_even_with_timing[Renew my license]`
- `test_missing_deadline_requires_a_corrected_answer[I will pay the phone bill tomorrow.-Pay the phone bill]`
- `test_missing_deadline_requires_a_corrected_answer[Submit the form by Friday.-Submit the form]`
- `test_short_quote_cannot_hide_deadline_or_borrow_one_from_another_sentence`
- `test_other_persons_plan_cannot_be_published_under_you`
- `test_other_persons_completion_requires_a_corrected_answer`
- `test_role_guard_does_not_reject_author_actions_outside_completion_matcher[I mailed the letter.-Mail the letter]`
- `test_role_guard_does_not_reject_author_actions_outside_completion_matcher[I renewed my passport and paid the bill.-Pay the bill]`
- `test_role_guard_does_not_reject_author_actions_outside_completion_matcher[I have just renewed my passport.-Renew my passport]`
- `test_role_validation_retries_with_specific_feedback`
- `test_unsupported_completed_activity_is_not_published_as_a_task_completion`

## Remaining failures

None in this 28-case rerun.

Full observed outputs: [live-results.json](final-summary/live-results.json). Automated output: [automated-output.txt](final-summary/automated-output.txt).
