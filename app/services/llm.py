"""LLM provider abstractions and a draft-reply pipeline with mock fallback.

`generate_draft_reply` is the entry point used by the service layer: it first
retrieves relevant knowledge base articles, then delegates the answer to the
configured LLM provider while enforcing a rate limit and gracefully falling
back to the deterministic mock provider when the real API is unavailable.
"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import get_settings
from app.services.rag import search_knowledge_base

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/auto"
DEFAULT_REQUEST_TIMEOUT = 60.0

SYSTEM_PROMPT = (
    "Ти — старший оператор служби підтримки SaaS-продукту NimbusDesk. "
    "Відповідай клієнту виключно українською мовою. Використовуй інформацію "
    "з наданого контексту статей бази знань; якщо відповідь у контексті не "
    "можна знайти, чесно зауваж це і попроси додаткові деталі. Будь ввічливим, "
    "лаконічним і структурованим. Обов'язково додавай посилання на використані "
    "статті у форматі Markdown: [Назва статті](url)."
)

MOCK_REPLY_PREFIX = (
    "[MOCK DRAFT] Дякуємо за звернення! "
    "Для вирішення вашого питання перегляньте наступні інструкції:"
)

# Guards outbound LLM calls: at most 60 concurrent requests at a time (60 RPM).
llm_semaphore = asyncio.Semaphore(60)


def _build_user_prompt(customer_message: str, articles: list[dict[str, Any]]) -> str:
    """Compose the user turn with the customer message and retrieved context."""
    if articles:
        context = "\n".join(
            f"{index}. {article['title']}\n"
            f"   {article['content']}\n"
            f"   Джерело: {article['url']}"
            for index, article in enumerate(articles, start=1)
        )
    else:
        context = "(релевантних статей не знайдено)"

    return (
        "Питання клієнта:\n"
        f"{customer_message}\n\n"
        "Контекст із бази знань:\n"
        f"{context}"
    )


class BaseLLMProvider(ABC):
    """Common interface implemented by all LLM providers."""

    @abstractmethod
    async def generate_reply(
        self, customer_message: str, articles: list[dict[str, Any]]
    ) -> str:
        """Return a draft support reply for the message grounded in ``articles``."""


class LLMProviderError(Exception):
    """Raised when an LLM provider cannot produce a reply."""


class OpenRouterLLMProvider(BaseLLMProvider):
    """LLM provider backed by the OpenRouter chat completions API."""

    def __init__(self, api_key: str, timeout: float = DEFAULT_REQUEST_TIMEOUT) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def generate_reply(
        self, customer_message: str, articles: list[dict[str, Any]]
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_user_prompt(customer_message, articles),
                },
            ],
            "temperature": 0.6,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    OPENROUTER_BASE_URL, headers=headers, json=payload
                )
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                f"OpenRouter request timed out after {self.timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code == 429:
            raise LLMProviderError(
                f"OpenRouter rate limit exceeded (HTTP 429): {response.text[:300]}"
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"OpenRouter returned HTTP {response.status_code}: {response.text[:300]}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                "OpenRouter returned a non-JSON response"
            ) from exc

        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            raise LLMProviderError(
                f"Unexpected OpenRouter response shape: {data!r}"
            ) from None
        return content


class MockLLMProvider(BaseLLMProvider):
    """Deterministic offline provider that simulates real LLM latency."""

    def __init__(
        self, min_delay: float = 5.0, max_delay: float = 30.0
    ) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay

    async def generate_reply(
        self, customer_message: str, articles: list[dict[str, Any]]
    ) -> str:
        # Simulate network round-trip and model generation latency.
        # ``customer_message`` is intentionally unused in mock mode.
        await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

        lines = [MOCK_REPLY_PREFIX]
        lines.extend(f"- [{article['title']}]({article['url']})" for article in articles)
        return "\n".join(lines)


def get_llm_provider(api_key: str | None) -> BaseLLMProvider:
    """Return the provider matching the configured API key.

    A non-empty key selects the real ``OpenRouterLLMProvider``; otherwise the
    deterministic ``MockLLMProvider`` is used so the service stays functional
    during development.
    """
    if api_key:
        return OpenRouterLLMProvider(api_key=api_key)
    logger.info("OPENROUTER_API_KEY is not set — using MockLLMProvider")
    return MockLLMProvider()


async def generate_draft_reply(customer_message: str) -> str:
    """Search the knowledge base and produce a draft support reply.

    The LLM call is rate-limited with a module-level semaphore. If the real
    provider fails (authentication error, network outage, malformed response),
    the service transparently falls back to the mock provider.
    """
    articles = search_knowledge_base(customer_message)
    provider = get_llm_provider(get_settings().openrouter_api_key)

    async with llm_semaphore:
        try:
            return await provider.generate_reply(customer_message, articles)
        except Exception:
            logger.exception(
                "LLM provider %r failed; falling back to MockLLMProvider",
                type(provider).__name__,
            )
            return await MockLLMProvider().generate_reply(customer_message, articles)
