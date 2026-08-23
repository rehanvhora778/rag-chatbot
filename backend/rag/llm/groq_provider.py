"""Groq — the implemented LLM provider.

Everything provider-specific about talking to Groq lives here: how a rate limit
is signalled, how usage is reported, how a streaming chunk is shaped, and which
models refuse image input. The rest of the project sees `complete` and `stream`.
"""
import logging
import re
import time
from typing import Iterator, Optional

from django.conf import settings

from rag.llm.base import LLMError, LLMResponse, Message, RateLimited, Usage

logger = logging.getLogger(__name__)

# A reasoning model narrating its thinking must never reach a document or an
# answer: it would be embedded and quoted back as if it were the file's own
# content. Stripped defensively even where reasoning is switched off, because
# "switched off" is a request, not a guarantee.
_THINK_BLOCK = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    text = _THINK_BLOCK.sub('', text or '').strip()
    if '<think>' in text.lower():
        # Thinking that never closed means the reply was cut off before the
        # answer began. Returning the fragment before it is better than
        # returning the model's deliberation.
        return text.lower().split('<think>', 1)[0].strip()
    return text


class GroqProvider:
    name = 'groq'

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None):
        self._api_key = api_key if api_key is not None else settings.GROQ_API_KEY
        self._model = model or settings.GROQ_MODEL
        self._temperature = (settings.GROQ_TEMPERATURE
                             if temperature is None else temperature)
        self._max_tokens = max_tokens or settings.GROQ_MAX_OUTPUT_TOKENS
        self._client = None

    @property
    def model(self) -> str:
        return self._model

    def supports_streaming(self) -> bool:
        return True

    # ── client ───────────────────────────────────────────────────
    def _get_client(self):
        if self._client is None:
            from groq import Groq

            if not self._api_key:
                raise LLMError(
                    'GROQ_API_KEY is not set. Add it to backend/.env — a free key '
                    'is available from https://console.groq.com/keys'
                )
            self._client = Groq(api_key=self._api_key)
            logger.info('Groq client initialised (model: %s)', self._model)
        return self._client

    # ── generation ───────────────────────────────────────────────
    def complete(self, messages: list[Message], *,
                 temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None) -> LLMResponse:
        import groq as groq_sdk

        client = self._get_client()
        payload = [m.as_dict() for m in messages]
        started = time.perf_counter()

        delay = 5
        attempts = 3

        for attempt in range(1, attempts + 1):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=payload,
                    temperature=self._temperature if temperature is None else temperature,
                    max_tokens=max_tokens or self._max_tokens,
                )
            except groq_sdk.RateLimitError as exc:
                if attempt == attempts:
                    logger.error('Groq rate limit: all %d attempts exhausted.', attempts)
                    raise RateLimited(
                        'The language model is rate limited. Wait a moment and '
                        'try again.'
                    ) from exc
                logger.warning('Groq rate limit (attempt %d/%d); retrying in %ds',
                               attempt, attempts, delay)
                time.sleep(delay)
                delay *= 2
            except groq_sdk.APIStatusError as exc:
                # A 404 here is almost always a retired model, which is the
                # failure this project has actually hit — and it is silent
                # unless someone says what it means.
                if exc.status_code == 404:
                    raise LLMError(
                        f'Groq does not recognise the model "{self._model}". It has '
                        'most likely been retired — check '
                        'https://console.groq.com/docs/models and update GROQ_MODEL.'
                    ) from exc
                raise LLMError(f'Groq returned {exc.status_code}: {exc}') from exc
            except Exception as exc:
                raise LLMError(f'Groq request failed: {exc}') from exc
            else:
                choice = response.choices[0]
                return LLMResponse(
                    text=strip_reasoning(choice.message.content or ''),
                    model=self._model,
                    provider=self.name,
                    usage=Usage.from_provider(getattr(response, 'usage', None)),
                    finish_reason=getattr(choice, 'finish_reason', '') or '',
                    latency_ms=round((time.perf_counter() - started) * 1000),
                )

        raise LLMError('Groq request failed after retries.')   # unreachable

    def stream(self, messages: list[Message], *,
               temperature: Optional[float] = None,
               max_tokens: Optional[int] = None) -> Iterator[str]:
        """Yield text fragments as they arrive.

        Not retried. A rate limit on the first token is worth raising
        immediately so the caller can show an error; retrying mid-stream would
        mean either replaying tokens the user has already seen or silently
        starting a different answer halfway through.
        """
        import groq as groq_sdk

        client = self._get_client()

        try:
            stream = client.chat.completions.create(
                model=self._model,
                messages=[m.as_dict() for m in messages],
                temperature=self._temperature if temperature is None else temperature,
                max_tokens=max_tokens or self._max_tokens,
                stream=True,
            )
        except groq_sdk.RateLimitError as exc:
            raise RateLimited('The language model is rate limited.') from exc
        except Exception as exc:
            raise LLMError(f'Groq stream failed to start: {exc}') from exc

        in_reasoning = False
        for chunk in stream:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content or ''
            if not piece:
                continue

            # Reasoning is filtered as it streams, not after: the whole point of
            # streaming is that the caller has already displayed what came
            # before, so a <think> block cannot be removed retrospectively.
            if '<think>' in piece.lower():
                in_reasoning = True
            if in_reasoning:
                if '</think>' in piece.lower():
                    in_reasoning = False
                    piece = piece.lower().split('</think>', 1)[1]
                    if piece:
                        yield piece
                continue

            yield piece

    # ── vision ───────────────────────────────────────────────────
    def read_image(self, image_b64: str, prompt: str,
                   mime_type: str = 'image/png', max_tokens: int = 600) -> str:
        """OCR a rendered page image with the configured vision model.

        Separate from `complete` because it is not the same capability: most
        Groq models are text-only and reject image input outright, so this uses
        GROQ_VISION_MODEL rather than the chat model.
        """
        import groq as groq_sdk

        # Images are the most rate-limited calls in the app; ride out a 429
        # rather than losing the page entirely.
        client = self._get_client().with_options(max_retries=5)
        payload = [{
            'role': 'user',
            'content': [
                {'type': 'image_url',
                 'image_url': {'url': f'data:{mime_type};base64,{image_b64}'}},
                {'type': 'text', 'text': prompt},
            ],
        }]

        try:
            response = client.chat.completions.create(
                model=settings.GROQ_VISION_MODEL,
                messages=payload,
                max_tokens=max_tokens,
                reasoning_effort='none',
            )
        except groq_sdk.BadRequestError as exc:
            # Not every vision model accepts reasoning_effort; retry plainly.
            if 'reasoning' not in str(exc).lower():
                raise
            response = client.chat.completions.create(
                model=settings.GROQ_VISION_MODEL,
                messages=payload,
                max_tokens=max_tokens,
            )

        return strip_reasoning(response.choices[0].message.content or '')
