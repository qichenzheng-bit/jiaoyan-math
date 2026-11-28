from types import SimpleNamespace as N
from app.services.video_source_context import source_entry, select_opening_source

def make(role="original", verified=True, primary=True, occurrences=None):
    link=N(occurrences=occurrences or [], original_question_number="4", provenance_role=role, role_verified=verified, is_primary=primary)
    source=N(title="2025年郑州大学数学分析",cohort_year="2025",exam_type="考研",source_type="exam",subject="数学分析")
    return source_entry(link,source,N(institution="郑州大学"))

def test_verified_original_precedes_reproduced_primary():
    original=make(primary=False)
    assert select_opening_source([make("reproduced"),original]) is original

def test_multiple_originals_without_primary_not_guessed():
    assert select_opening_source([make(primary=False),make(primary=False)]) is None

def test_multiple_positions_no_guessed_question_number():
    assert make(occurrences=[{"original_question_number":"3"},{"original_question_number":"4"}])["question_number"]==""
    assert make(occurrences=[{"original_question_number":"5"}])["question_number"]=="5"

def test_missing_source():
    assert select_opening_source([]) is None
