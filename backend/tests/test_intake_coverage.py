import pytest
from app.api.intelligence import validate_question_coverage

def test_explicit_exercise_headers_cannot_be_omitted():
    text="习题 29.1\n题目\n答案\n习题 29.2\n题目"
    with pytest.raises(ValueError,match="29.2"):
        validate_question_coverage(text,[{"kind":"question","title":"习题 29.1"}])
    validate_question_coverage(text,[{"kind":"question","title":"习题 29.1"},{"kind":"question","original_question_number":"29.2"}])
