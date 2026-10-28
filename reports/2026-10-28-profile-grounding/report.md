# Profile fact coverage and pronoun context

The October 27 fictional journal regression organized but omitted Stewy's photography interest and Leila's architecture studies. Output validation previously checked each returned memory, without requiring these explicit source facts to be represented. Response-limit fallback could also divide a paragraph so a pronoun's named antecedent was outside the section, while name validation required the name to appear in that section.

Changes:

- Send exact source hints for affirmative learning/studying passages; ask the model to retain hobbies as interests and ongoing education as context, separately.
- Validate category, source-topic words and overlapping exact evidence for supported profile actors. Missing facts receive specific corrective feedback instead of silently disappearing.
- Carry up to 1,200 characters of earlier text from the same source paragraph as identity context when splitting. That text may verify a name but cannot supply an evidence quote. Full-entry verification still requires every name and quote to appear in the original entry.
- Recheck the combined sections for demonstrated profile gaps. Recover only affected paragraphs using bounded sections, then deduplicate retained facts. Publication remains atomic and the forty-detail limit remains enforced.
- Skip forced pronoun attribution when multiple people or an unnamed relative make the actor ambiguous. Questions, negations, uncertain statements and unnamed subjects do not require a new profile fact. Directly written multiword names remain intact.

These are bounded source checks for explicit learning/studying forms and a directly coordinated hobby, not general coreference resolution or a promise to extract every possible fact. Actor resolution and the factual extraction remain model responsibilities; local code does not manufacture memories or infer a person's gender. Pronoun coverage can use a named profile already supported within the paragraph; completely omitted or ambiguous actors are not assigned by guesswork.

Verification:

- 335 backend tests passed, with one existing Starlette/httpx deprecation warning.
- Nineteen new regression cases cover both original omissions, separate education/hobby categories, targeted retry and automatic publication, section and response-limit fallback, cross-section recovery without duplicates, exact evidence restrictions, paragraph reset, multiword names, ambiguous actors, questions/negations and unnamed subjects.
- Existing atomic-publication, source validation, personal-task timing, recurrence, identity and source-history tests remain green.
- No frontend change is required. Test writes use isolated temporary databases.

A fresh full fictional journal run is recorded under `reports/2026-10-27-optimization/` with label `profile-grounding-live`; its outcome is recorded below when complete. Earlier failed runs remain retained as failures.

The focused live two-paragraph regression passed in 44.814 seconds, retaining both original missing facts. The first fresh full journal run recovered photography and architecture but omitted Leila's pottery interest (342.759 seconds; five recorded provider responses, with response-limit fallback). That run remains a failed broader gate. The coverage check was then extended to the coordinated hobby, with a dedicated regression case; a complete fresh rerun uses label `profile-grounding-verified`.

Final live gate: **PASS**. `profile-grounding-verified.json` records an organized entry with no acceptance issues, including Stewy/interest/photography, Leila/context/architecture, and Leila/interest/pottery. The existing birthday correction, personal intentions, weekly/monthly repeats and authored completion assertions also pass. Every checked fact retains an exact original source quote. The full sample took **345.869 seconds**; six completed provider responses were recorded. The benchmark does not capture failed network attempts in that response count, so six is not a complete attempt count. This is a reliability improvement, not evidence that long-entry latency is solved.

The final current-source Python suite passed 335 tests. The focused live sample and complete sample both used fictional isolated databases. The ordinary local preview was restarted with the changes; existing journal entries have not been silently edited or backfilled. Newly organized/reorganized entries use the new checks.
