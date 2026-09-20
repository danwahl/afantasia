"""Inspect provider for OpenRouter's alpha Decisions endpoint.

Models served there (typesafe/jev-*) are not reachable over chat/completions and
emit no free text. A request is a set of `questions`, each with a closed answer
space -- `noul` (boolean), `choice` (pick a key from a supplied map), or `score`
-- plus a `state` blob of context. The reply names the winning key and gives a
probability over the whole space.

That only lines up with the cube task, where the answer is one of the six colors
already listed in the prompt, so the option map tells the model nothing the other
models are not told. Chess would require handing over the legal-move list, which
is the answer key; spell has an unbounded answer space. See README.

The chat transcript becomes `state`, the colors named in the prompt become the
`choice` criteria, and the reply is re-wrapped as "ANSWER: <color>" so the task's
existing pattern scorer reads it unchanged.
"""

import os
import re
import time
from typing import Any

import httpx
from inspect_ai.model import (
    ChatMessage,
    GenerateConfig,
    ModelAPI,
    ModelCall,
    ModelOutput,
    ModelUsage,
    modelapi,
)
from inspect_ai.tool import ToolChoice, ToolInfo
from typing_extensions import override

OPENROUTER_API_KEY = "OPENROUTER_API_KEY"

DEFAULT_BASE_URL = "https://openrouter.ai/api/alpha/decisions"

# The six colors the cube prompt lists, in "- Front face: red" form. Also the
# exact answer space the question is drawn from.
FACE_COLOR = re.compile(r"^- (?:\w+) face: (\w+)$", re.MULTILINE)

QUESTION_KEY = "answer"


class DecisionsError(Exception):
    pass


@modelapi(name="decisions")
class DecisionsAPI(ModelAPI):
    """Reaches a decisions-only model as if it were a chat model."""

    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        config: GenerateConfig = GenerateConfig(),
        **model_args: Any,
    ) -> None:
        super().__init__(
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            api_key_vars=[OPENROUTER_API_KEY],
            config=config,
        )
        if self.api_key is None:
            self.api_key = os.environ.get(OPENROUTER_API_KEY)
        if self.api_key is None:
            raise RuntimeError(f"{OPENROUTER_API_KEY} is not set.")
        self.endpoint: str = base_url or DEFAULT_BASE_URL
        self.client = httpx.AsyncClient(timeout=120)
        self.model_args = model_args

    @override
    async def generate(
        self,
        input: list[ChatMessage],
        tools: list[ToolInfo],
        tool_choice: ToolChoice,
        config: GenerateConfig,
    ) -> tuple[ModelOutput | Exception, ModelCall]:
        prompt = "\n\n".join(message.text for message in input)
        criteria = choice_criteria(prompt)

        request: dict[str, Any] = {
            "model": self.model_name,
            "questions": {
                QUESTION_KEY: {
                    "instructions": instructions(input),
                    "type": "choice",
                    "criteria": criteria,
                }
            },
            "state": {"transcript": prompt},
            **self.model_args,
        }

        start = time.monotonic()
        response = await self.client.post(
            self.endpoint,
            json=request,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        elapsed = time.monotonic() - start
        payload = response.json()
        call = ModelCall.create(request=request, response=payload, time=elapsed)

        if response.status_code != 200:
            message = payload.get("error", {}).get("message", response.text)
            return DecisionsError(f"{response.status_code}: {message}"), call

        answer = payload["answers"][QUESTION_KEY]
        usage = payload.get("usage", {})

        output = ModelOutput.from_content(
            model=payload.get("model", self.model_name),
            # The scorer reads the task's answer format, not this endpoint's.
            content=f"ANSWER: {answer['choice']}",
        )
        output.usage = ModelUsage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        )
        # Retained for calibration analysis; the endpoint scores every option.
        output.metadata = {
            "probabilities": answer.get("probabilities"),
            "confidence": answer.get("confidence"),
            "criteria": sorted(criteria),
        }
        return output, call

    @override
    def should_retry(self, ex: Exception) -> bool:
        if isinstance(ex, httpx.HTTPError):
            return True
        if isinstance(ex, DecisionsError):
            return ex.args[0].startswith(("429", "5"))
        return False

    @override
    def connection_key(self) -> str:
        return f"decisions:{self.api_key}"


def instructions(input: list[ChatMessage]) -> str:
    """The question to decide: the last user turn, which carries the ask."""
    for message in reversed(input):
        if message.role == "user":
            return message.text
    return input[-1].text


def choice_criteria(prompt: str) -> dict[str, str]:
    """The answer space, read back out of the prompt the task rendered.

    The cube prompt names all six colors, so this adds no information the other
    models do not get. A prompt that names none is not a cube prompt and has no
    closed answer space this endpoint can be asked about.
    """
    colors = sorted(set(FACE_COLOR.findall(prompt)))
    if not colors:
        raise DecisionsError(
            "No cube face colors found in the prompt, so there is no closed "
            "answer space to offer. This provider only supports the cube task."
        )
    return {color: color for color in colors}
