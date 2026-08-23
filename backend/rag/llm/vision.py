"""Reading a page image — OCR for scanned PDFs.

Kept apart from the provider interface because vision is optional: a provider
that cannot see images is still a perfectly good LLM provider, and the
``LLMProvider`` protocol would be claiming a capability most implementations
will not have. Asked for rather than assumed, so the failure is a clear message
about configuration instead of an AttributeError from inside extraction.
"""


def read_image(image_b64: str, prompt: str, mime_type: str = 'image/png',
               max_tokens: int = 600) -> str:
    """OCR a rendered page image. Needs a provider with vision support."""
    from rag.registry import get_llm

    provider = get_llm()
    if not hasattr(provider, 'read_image'):
        raise NotImplementedError(
            f'The {provider.name} provider cannot read images, so scanned pages '
            "cannot be OCR'd. Use LLM_PROVIDER=groq for that."
        )
    return provider.read_image(image_b64, prompt, mime_type, max_tokens)
