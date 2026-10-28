"""Opt-in live regression using the fictional compound-task journal entry."""
import sys
from unittest.mock import patch
from benchmark import CASES, run, inference

CASES.append({
    'id': 'compound_journal',
    'text': '''Today was a mix of catching up and trying to get my own life organized.

I had coffee with stewy, who told me he’s learning photography. He wants to try taking portraits but hasn’t picked a camera yet. I promised I’d send him that beginner’s guide I bookmarked.

I also met someone new, Leila, at the café. She’s studying architecture and loves making pottery. Her birthday is November 12. We talked about checking out a ceramics class sometime, but nothing is booked.

Maya corrected me about her birthday—it’s April 18, not April 8. She’s still really into hiking. I need to send Maya the trail guide tomorrow.

For myself, I need to renew my driver’s license by October 30 and book a dentist appointment. I should water the plants every Saturday and pay rent on the first of each month. Remind me to look into a better desk chair, though I haven’t decided what kind.

I paid the electricity bill today. Maya renewed her passport, but I still need to renew mine.

I might start running every morning, but I’m not committing to that yet. Mostly, I felt a little overwhelmed today and wanted some room to breathe.''',
    'people': ['stewy', 'Leila'],
    'personal': ['license', 'dentist', 'plants', 'rent', 'chair'],
    'birthday': True,
    'completed': True,
    'repeats': ['weekly', 'monthly'],
    'facts': [('stewy', 'interest', 'photography'), ('Leila', 'context', 'architecture'), ('Leila', 'interest', 'pottery'), ('Leila', 'birthday', '12')],
    'forbid_personal': ['room to breathe'],
})
original_validate = inference.validate_meaning

def validate_with_progress(result, note):
    try:
        original_validate(result, note)
    except inference.ExtractionValidationError as exc:
        print('Validation feedback:', str(exc), flush=True)
        raise

with patch.object(inference, 'validate_meaning', validate_with_progress):
    run(sys.argv[1] if len(sys.argv) > 1 else 'compound-deadline-verified', ['compound_journal'])
