"""Keyword-based retrieval over the knowledge base seed data.

Implements a simple lexical search over ``data/kb_articles.json``: the query
and each article are split into word tokens and ranked by overlap (with a
weight bonus for title matches). When nothing matches, the first articles are
returned so the LLM still has context material.
"""

import json
import re
from typing import Any

from app.config import PROJECT_ROOT

KB_ARTICLES_PATH = PROJECT_ROOT / "data" / "kb_articles.json"
FALLBACK_CONTEXT_LIMIT = 2

_TOKEN_PATTERN = re.compile(r"[a-zа-яіїєґ0-9']+")


def _tokenize(text: str) -> set[str]:
    """Lowercase the text and split it into word tokens (EN/UK)."""
    return set(_TOKEN_PATTERN.findall(text.lower()))


def _load_articles() -> list[dict[str, Any]]:
    """Load and return the knowledge base articles from disk."""
    with KB_ARTICLES_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def search_knowledge_base(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Return up to ``limit`` most relevant articles for ``query``.

    Relevance is computed as the token overlap between the query and each
    article title + content; title hits are weighted three times higher than
    body hits. If no article shares any token with the query, the function
    returns up to ``FALLBACK_CONTEXT_LIMIT`` leading articles instead.
    """
    if limit < 1:
        return []

    articles = _load_articles()
    query_tokens = _tokenize(query)
    if not query_tokens:
        return articles[: min(limit, FALLBACK_CONTEXT_LIMIT)]

    ranked: list[tuple[int, dict[str, Any]]] = []
    for article in articles:
        title_tokens = _tokenize(article["title"])
        body_tokens = _tokenize(article["content"])
        score = len(query_tokens & body_tokens) + 3 * len(query_tokens & title_tokens)
        if score > 0:
            ranked.append((score, article))

    ranked.sort(key=lambda pair: pair[0], reverse=True)

    if ranked:
        return [article for _, article in ranked[:limit]]

    context_count = min(limit, FALLBACK_CONTEXT_LIMIT)
    return articles[:context_count]
