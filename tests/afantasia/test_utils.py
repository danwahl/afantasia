"""Tests for the utils module."""

import re

from afantasia.tasks.utils import ANSWER_MESSAGE, ANSWER_REGEX, CHESS_ANSWER_REGEX


def test_answer_regex_extracts_simple_word():
    """Test that the regex extracts a simple word answer."""
    match = re.search(ANSWER_REGEX, "blue")
    assert match is not None
    assert match.group(1) == "blue"


def test_answer_regex_extracts_with_prefix():
    """Test that the regex extracts answer with ANSWER: prefix."""
    match = re.search(ANSWER_REGEX, "ANSWER: red")
    assert match is not None
    assert match.group(1) == "red"


def test_answer_regex_extracts_without_space():
    """Test extraction without space after colon."""
    match = re.search(ANSWER_REGEX, "ANSWER:green")
    assert match is not None
    assert match.group(1) == "green"


def test_answer_regex_extracts_chess_move():
    """Test that the regex extracts chess notation."""
    match = re.search(ANSWER_REGEX, "ANSWER: Nf3")
    assert match is not None
    assert match.group(1) == "Nf3"


def test_answer_regex_extracts_alphanumeric():
    """Test that the regex extracts alphanumeric answers."""
    match = re.search(ANSWER_REGEX, "e4")
    assert match is not None
    assert match.group(1) == "e4"


def test_answer_regex_extracts_after_leading_newline():
    """A response opening with a newline is still answer-only."""
    match = re.search(ANSWER_REGEX, "\nANSWER: erolklof")
    assert match is not None
    assert match.group(1) == "erolklof"


def test_answer_regex_extracts_answer_before_truncation():
    """The answer counts when the model ran on past it and was cut off."""
    match = re.search(ANSWER_REGEX, " rotanes\nANSWER")
    assert match is not None
    assert match.group(1) == "rotanes"


def test_answer_regex_tolerates_trailing_punctuation():
    """Trailing punctuation or decoration does not invalidate the answer."""
    assert re.search(ANSWER_REGEX, "ANSWER: blue.").group(1) == "blue"
    assert re.search(ANSWER_REGEX, " EMADAM ⚡️\n").group(1) == "EMADAM"


def test_answer_regex_tolerates_code_fence():
    """Some models fence the answer; that is still an answer-only response."""
    assert re.search(ANSWER_REGEX, "```\nANSWER: purple\n```").group(1) == "purple"


def test_answer_regex_rejects_reasoning_before_answer():
    """Reasoning first breaks the task's core constraint; it is not an answer."""
    assert re.search(ANSWER_REGEX, "Let me think...\nANSWER: blue") is None


def test_answer_regex_rejects_extra_text():
    """Test that the regex rejects extra text after answer."""
    # The regex requires the answer to be the whole line
    match = re.search(ANSWER_REGEX, "ANSWER: blue is the color")
    assert match is None


def test_chess_regex_extracts_san_tokens():
    """The chess pattern keeps its SAN character class and prefix matching."""
    assert re.search(CHESS_ANSWER_REGEX, "ANSWER: e8=Q+").group(1) == "e8=Q+"
    assert re.search(CHESS_ANSWER_REGEX, "\nANSWER: O-O").group(1) == "O-O"
    # Commentary after the move is tolerated (unlike the single-word tasks).
    assert re.search(CHESS_ANSWER_REGEX, "Nf3 is best").group(1) == "Nf3"


def test_answer_message_contains_critical_instructions():
    """Test that the answer message contains the expected format."""
    assert "ANSWER: $ANSWER" in ANSWER_MESSAGE
    assert "CRITICAL INSTRUCTIONS" in ANSWER_MESSAGE
