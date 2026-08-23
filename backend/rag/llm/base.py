"""The LLM provider contract.

Groq is the only implementation in this repository, and that is a deliberate
choice rather than an unfinished one. An adapter nobody has run against a real
endpoint is not support for a provider — it is three files that will not work
the first time someone needs them, and a claim in a README that turns out to be
false. The registry exists so adding one is a new file and a settings change,
which is the property worth having.

What the interface has to cover, and why each piece is here rather than in the
caller:

* **Streaming.** Phase 8 streams answers to the browser. If streaming were
  bolted on later, every provider would grow its own way of doing it and the
  chat service would branch on which one is active.
* **Token usage.** Recorded on every message so the analytics dashboard and the
  evaluation harness can report cost without a second logging path. Providers
  report it differently and some not at all, so it is normalised here.
* **Retries.** Rate limits are the normal failure of a free-tier LLM, not an
  exceptional one. Handling them per-provider keeps the backoff next to the
  exception type that actually signals them.
"""
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional, Protocol, runtime_checkable


@dataclass
class Message:
    """One chat message in the provider-neutral shape."""

    role: str          # 'system' | 'user' | 'assistant'
    content: str

    def as_dict(self) -> dict[str, str]:
        return {'role': self.role, 'content': self.content}


@dataclass
class Usage:
    """Token accounting, as far as the provider reports it.

    All fields optional because not every provider returns usage, and a zero
    would be indistinguishable from "it did not say" — which matters when the
    number is being summed into a cost report.
    """

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    @classmethod
    def from_provider(cls, raw: Any) -> 'Usage':
        if raw is None:
            return cls()
        get = (raw.get if isinstance(raw, dict) else lambda k, d=None: getattr(raw, k, d))
        return cls(
            prompt_tokens=get('prompt_tokens'),
            completion_tokens=get('completion_tokens'),
            total_tokens=get('total_tokens'),
        )


@dataclass
class LLMResponse:
    """A completed generation."""

    text: str
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = ''
    latency_ms: Optional[int] = None

    @property
    def truncated(self) -> bool:
        """Did the model stop because it ran out of room?

        Worth surfacing: a truncated answer often loses its final citations,
        which reads as a grounding failure when it is a token-budget one.
        """
        return self.finish_reason in ('length', 'max_tokens')


class LLMError(Exception):
    """The provider could not produce an answer."""


class RateLimited(LLMError):
    """The provider refused because of a rate limit, after retries."""


@runtime_checkable
class LLMProvider(Protocol):
    """Text generation, with or without streaming."""

    name: str

    def complete(self, messages: list[Message], *,
                 temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None) -> LLMResponse:
        """Generate a full response."""
        ...

    def stream(self, messages: list[Message], *,
               temperature: Optional[float] = None,
               max_tokens: Optional[int] = None) -> Iterator[str]:
        """Yield the response in pieces as it is produced.

        Yields text fragments, not provider chunk objects, so the caller never
        has to know how a given provider frames a delta.
        """
        ...

    def supports_streaming(self) -> bool: ...

    @property
    def model(self) -> str:
        """The model this provider is configured to call."""
        ...
