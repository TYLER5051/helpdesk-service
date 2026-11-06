"""Keyword-based retrieval over the knowledge base seed data.

Implements a simple lexical search over ``data/kb_articles.json``: the query
and each article are split into word tokens and ranked by overlap (with a
weight bonus for title matches). When nothing matches, the first articles are
returned so the LLM still has context material.

The seed articles are parsed and tokenized once and cached in memory
(``functools.lru_cache``): RAG retrieval runs on hot async code paths
(webhook background tasks, operator UI), so repeated synchronous disk I/O is
avoided. Restart the process after editing ``kb_articles.json``.
"""

import json
import re
from functools import lru_cache
from typing import Any

from app.config import PROJECT_ROOT

KB_ARTICLES_PATH = PROJECT_ROOT / "data" / "kb_articles.json"
FALLBACK_CONTEXT_LIMIT = 2

_TOKEN_PATTERN = re.compile(r"[a-zа-яіїєґ0-9']+")

IndexedArticle = tuple[dict[str, Any], set[str], set[str]]


def _tokenize(text: str) -> set[str]:
    """Lowercase the text and split it into word tokens (EN/UK)."""
    return set(_TOKEN_PATTERN.findall(text.lower()))


@lru_cache(maxsize=1)
def _load_index() -> tuple[IndexedArticle, ...]:
    """Load and index articles once; the result is cached process-wide."""
    with KB_ARTICLES_PATH.open(encoding="utf-8") as file:
        articles = json.load(file)
    return tuple(
        (article, _tokenize(article["title"]), _tokenize(article["content"]))
        for article in articles
    )


def search_knowledge_base(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Return up to ``limit`` most relevant articles for ``query``.

    Relevance is computed as the token overlap between the query and each
    article title + content; title hits are weighted three times higher than
    body hits. If no article shares any token with the query, the function
    returns up to ``FALLBACK_CONTEXT_LIMIT`` leading articles instead.
    """
    if limit < 1:
        return []

    indexed = _load_index()
    query_tokens = _tokenize(query)

    if not indexed or not query_tokens:
        fallback_count = min(limit, FALLBACK_CONTEXT_LIMIT)
        return [article for article, _title, _body in indexed[:fallback_count]]

    ranked: list[tuple[int, dict[str, Any]]] = []
    for article, title_tokens, body_tokens in indexed:
        score = len(query_tokens & body_tokens) + 3 * len(query_tokens & title_tokens)
        if score > 0:
            ranked.append((score, article))

    ranked.sort(key=lambda pair: pair[0], reverse=True)

    if ranked:
        return [article for _, article in ranked[:limit]]

    context_count = min(limit, FALLBACK_CONTEXT_LIMIT)
    return [article for article, _title, _body in indexed[:context_count]]

