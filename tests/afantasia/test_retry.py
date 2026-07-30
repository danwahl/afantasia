"""Tests for the retry-on-truncation solver."""

import pytest
from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageUser,
    ModelName,
    ModelOutput,
)
from inspect_ai.solver import TaskState

from afantasia.solvers.retry import generate_until_answered

PROMPT = "what color is the top face?"


def _make_generate(scripted):
    """A fake generate() returning (completion, stop_reason) pairs in order."""
    calls = {"n": 0, "messages": []}

    async def fake_generate(state, **kwargs):
        content, stop_reason = scripted[min(calls["n"], len(scripted) - 1)]
        calls["n"] += 1
        # Record what the model was shown on this attempt.
        calls["messages"].append([m.text for m in state.messages])
        output = ModelOutput.from_content("mockllm/model", content)
        output.choices[0].stop_reason = stop_reason
        state.output = output
        state.messages.append(ChatMessageAssistant(content=content))
        return state

    return fake_generate, calls


def _state():
    return TaskState(
        model=ModelName("mockllm/model"),
        sample_id="x",
        epoch=1,
        input=PROMPT,
        messages=[ChatMessageUser(content=PROMPT)],
    )


@pytest.mark.asyncio
async def test_retries_until_answered():
    """Re-asks after a truncated response and keeps the answer that arrives."""
    generate, calls = _make_generate(
        [
            ("I need to track the cube's faces.\nInitial state:\n-", "max_tokens"),
            ("Let me work through the rotations", "max_tokens"),
            ("ANSWER: silver", "stop"),
        ]
    )
    state = await generate_until_answered(max_attempts=3)(_state(), generate)

    assert calls["n"] == 3
    assert state.output.completion == "ANSWER: silver"


@pytest.mark.asyncio
async def test_nudge_is_appended_before_each_re_attempt():
    """The retry restates the format constraint in a new user turn."""
    generate, calls = _make_generate(
        [("Let me track the faces: front is", "max_tokens"), ("ANSWER: gray", "stop")]
    )
    state = await generate_until_answered(max_attempts=2, nudge="answer immediately")(
        _state(), generate
    )

    assert calls["messages"][0] == [PROMPT]
    assert calls["messages"][1] == [
        PROMPT,
        "Let me track the faces: front is",
        "answer immediately",
    ]
    # No nudge after the answer arrives.
    assert sum(1 for m in state.messages if m.role == "user") == 2


@pytest.mark.asyncio
async def test_stops_on_first_answer():
    """No extra generations once the model answers immediately."""
    generate, calls = _make_generate([("ANSWER: blue", "stop"), ("unused", "stop")])
    state = await generate_until_answered(max_attempts=3)(_state(), generate)

    assert calls["n"] == 1
    assert state.output.completion == "ANSWER: blue"


@pytest.mark.asyncio
async def test_wrong_answer_is_not_retried():
    """A prompt answer that happens to be wrong is a real result, not a failure."""
    generate, calls = _make_generate(
        [("ANSWER: teal", "stop"), ("ANSWER: red", "stop")]
    )
    state = await generate_until_answered(max_attempts=3)(_state(), generate)

    assert calls["n"] == 1
    assert state.output.completion == "ANSWER: teal"


@pytest.mark.asyncio
async def test_answer_before_truncation_is_not_retried():
    """A complete answer line followed by run-on text is already scorable."""
    generate, calls = _make_generate([(" rotanes\nANSWER", "max_tokens")])
    state = await generate_until_answered(max_attempts=3)(_state(), generate)

    assert calls["n"] == 1
    assert state.output.completion == " rotanes\nANSWER"


@pytest.mark.asyncio
async def test_partial_final_line_is_not_an_answer():
    """Text after the last newline was cut mid-token, so it cannot be the answer."""
    generate, calls = _make_generate(
        [
            ("Let me set up the cube.\nFront: white\nTop", "max_tokens"),
            ("ANSWER: navy", "stop"),
        ]
    )
    state = await generate_until_answered(max_attempts=2)(_state(), generate)

    assert calls["n"] == 2
    assert state.output.completion == "ANSWER: navy"


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts():
    """A model that never complies exhausts its attempts and is scored as it fell."""
    generate, calls = _make_generate(
        [
            ("I need to track the cube's faces through", "max_tokens"),
            ("Working through the rotations step by", "max_tokens"),
        ]
    )
    state = await generate_until_answered(max_attempts=2)(_state(), generate)

    assert calls["n"] == 2
    assert state.output.completion == "Working through the rotations step by"
    assert str(state.output.stop_reason) == "max_tokens"


@pytest.mark.asyncio
async def test_single_attempt_makes_no_retry():
    """max_attempts=1 is exactly the no-retry behavior."""
    generate, calls = _make_generate([("truncated reasoning", "max_tokens")])
    state = await generate_until_answered(max_attempts=1)(_state(), generate)

    assert calls["n"] == 1
    assert state.output.completion == "truncated reasoning"
