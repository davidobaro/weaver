# Compound-task deadline validation fix

The journal sentence “I need to renew my driver’s license by October 30 and book a dentist appointment” exposed a false validation failure. The old check required every personal task in the sentence to retain any date found anywhere in that sentence. A correctly undated dentist task therefore triggered “A personal item lost its stated deadline,” exhausting corrective retries and pausing publication of the entire entry.

The timing validator now selects the task's own coordinated action clause, using its exact evidence location and action-word overlap when evidence spans multiple tasks. It splits conjunctions and comma lists only before a clear new action. Object lists such as “buy milk and bread tomorrow” stay together. Explicit leading timing such as “Tomorrow I need to renew my passport and book a dentist appointment” still applies to the coordinated intentions. Partial evidence cannot hide a deadline later in the same action clause.

This is a bounded local grammatical check, not a general natural-language parser. It preserves source validation and the existing corrective retry behavior; it does not fabricate deadlines for undated actions or publish partial results after a validation failure.

Verification: 314 Python tests pass (one existing Starlette/httpx deprecation warning). Eleven new regression cases cover short and broad evidence, forward/backward deadline leakage, comma and conjunction lists, genuinely omitted deadlines, shared leading dates, object lists, and the complete save/extract/publish/suggestion flow. The save-flow test confirms the dated passport task and undated dentist task remain separate and use one provider request.

The opt-in fictional live regression is `deadline_regression.py`; it uses a temporary database, not the personal journal. Original eight-case benchmark files remain a historical record of the earlier optimization pass.

A direct live Nebius extraction of the exact failing compound sentence passed in 11.18 seconds. It returned “renew my driver’s license by October 30” and a separate “Book dentist appointment” with no date. The local preview was restarted with the updated backend after the old in-flight extraction finished.

The first full-entry live run organized successfully but omitted the coordinated dentist task (527.514 seconds, ten requests). That exposed a second gap: the explicit-intention coverage check treated both coordinated actions as one span. Coverage now checks each clear action clause separately, including entries prefixed “For myself,”. A mocked full save-flow regression verifies targeted feedback and successful publication after a genuine omission, without treating the undated dentist task as a missing-deadline error. The first live result is retained as compound-deadline-fix.json rather than presented as a passing case.

After restarting the corrected backend, the existing saved sample entry was retried through the normal `/api/notes/{id}/organize` endpoint. It reached `organized`. The actual For you response contains one license card due October 30, 2026 and one dentist card with no due date, both linked to that entry. No original writing was edited or replaced.

The second isolated full-entry run also organized and retained both coordinated tasks with the correct dates (242.115 seconds, three requests). It did not pass the broader acceptance matrix: it omitted Stewy's photography interest and Leila's architecture context. Those profile omissions are separate from the fixed deadline/compound-task issue and remain unresolved; this run must not be represented as a full extraction-quality pass. See compound-deadline-verified.json for the complete fictional results.
