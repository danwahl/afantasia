"""Tests for the utils module."""

import re

from afantasia.tasks.utils import ANSWER_MESSAGE, ANSWER_REGEX


def test_answer_regex_extracts_simple_word():
    """Test that the regex extracts a simple word answer."""
    match = re.match(ANSWER_REGEX, "blue")
    assert match is not None
    assert match.group(3) == "blue"


def test_answer_regex_extracts_with_prefix():
    """Test that the regex extracts answer with ANSWER: prefix."""
    match = re.match(ANSWER_REGEX, "ANSWER: red")
    assert match is not None
    assert match.group(3) == "red"


def test_answer_regex_extracts_without_space():
    """Test extraction without space after colon."""
    match = re.match(ANSWER_REGEX, "ANSWER:green")
    assert match is not None
    assert match.group(3) == "green"


def test_answer_regex_extracts_chess_move():
    """Test that the regex extracts chess notation."""
    match = re.match(ANSWER_REGEX, "ANSWER: Nf3")
    assert match is not None
    assert match.group(3) == "Nf3"


def test_answer_regex_extracts_alphanumeric():
    """Test that the regex extracts alphanumeric answers."""
    match = re.match(ANSWER_REGEX, "e4")
    assert match is not None
    assert match.group(3) == "e4"


def test_answer_regex_rejects_multiline():
    """Test that the regex rejects multiline responses."""
    match = re.match(ANSWER_REGEX, "Let me think...\nANSWER: blue")
    assert match is None


def test_answer_regex_rejects_extra_text():
    """Test that the regex rejects extra text after answer."""
    # The regex requires end of string after the word
    match = re.match(ANSWER_REGEX, "ANSWER: blue is the color")
    assert match is None


def test_answer_message_contains_critical_instructions():
    """Test that the answer message contains the expected format."""
    assert "ANSWER: $ANSWER" in ANSWER_MESSAGE
    assert "CRITICAL INSTRUCTIONS" in ANSWER_MESSAGE
