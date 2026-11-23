import pytest

from app.agents.language import CONFIDENT_THRESHOLD, detect_language


@pytest.mark.parametrize(
    ("text", "expected_language"),
    [
        ("Je veux être ingénieur.", "fr"),
        ("شنوة شروط القبول في IIT؟", "tn-arabic"),
        ("nheb nwali ingenieur chnoua tansahni", "arabizi"),
        ("Nheb formation en informatique ama ma3andich info", "mixed"),
        ("asdf qwerty", "unknown"),
    ],
)
def test_detect_language_for_supported_inputs(text, expected_language):
    detection = detect_language(text)

    assert detection.language == expected_language
    assert (detection.confidence >= CONFIDENT_THRESHOLD) == (expected_language != "unknown")
