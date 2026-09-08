"""
Unit Tests for the Knowledge Graph Route's Related-Articles Endpoint
=====================================================================

``GET /knowledge-graph/related-articles/{article_id}`` powers the article
reader's "Related coverage" rail: given an article id, find the entities
it mentions and return other articles that mention those same entities.
"""

import sqlite3
from unittest.mock import patch

import pytest

import src.api.routes.knowledge_graph as knowledge_graph
from src.repositories.article_repository import ArticleRepository
from src.models.article import ArticleCreate


async def _seed_article(repository: ArticleRepository, title: str, url: str) -> int:
    article = await repository.create(
        ArticleCreate(
            title=title,
            url=url,
            content="Some tech news content, long enough to be meaningful.",
            summary="A short summary.",
            source="Test Source",
        )
    )
    return article.id


def _seed_entities(db_path: str, mentions: list[tuple[int, str, str, int]]) -> None:
    """``mentions`` is a list of ``(article_id, entity_name, entity_type, position)``."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS entities ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, "
            "type TEXT NOT NULL, mention_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS entity_mentions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER NOT NULL, "
            "entity_id INTEGER NOT NULL, position INTEGER, "
            "UNIQUE(article_id, entity_id))"
        )
        entity_ids: dict[str, int] = {}
        for article_id, name, etype, position in mentions:
            if name not in entity_ids:
                cur = conn.execute(
                    "INSERT INTO entities (name, type, mention_count) VALUES (?, ?, 1)",
                    (name, etype),
                )
                entity_ids[name] = cur.lastrowid
            conn.execute(
                "INSERT INTO entity_mentions (article_id, entity_id, position) "
                "VALUES (?, ?, ?)",
                (article_id, entity_ids[name], position),
            )
        conn.commit()


@pytest.fixture
def repository(temp_db_path):
    return ArticleRepository(db_path=temp_db_path)


@pytest.mark.asyncio
async def test_returns_articles_sharing_an_entity(repository, temp_db_path):
    source_id = await _seed_article(repository, "OpenAI ships GPT-5", "https://example.com/a1")
    related_id = await _seed_article(repository, "OpenAI raises funding", "https://example.com/a2")
    unrelated_id = await _seed_article(repository, "Unrelated story", "https://example.com/a3")

    _seed_entities(
        temp_db_path,
        [
            (source_id, "OpenAI", "company", 0),
            (related_id, "OpenAI", "company", 0),
            (unrelated_id, "Anthropic", "company", 0),
        ],
    )

    with patch.object(knowledge_graph, "_resolve_db_path", return_value=temp_db_path):
        response = await knowledge_graph.get_related_articles(source_id, limit=6)

    assert response["article_id"] == source_id
    assert response["primary_entity"]["name"] == "OpenAI"
    returned_ids = [a["id"] for a in response["articles"]]
    assert related_id in returned_ids
    assert unrelated_id not in returned_ids
    assert source_id not in returned_ids
    assert response["articles"][0]["title"] == "OpenAI raises funding"
    assert response["articles"][0]["source"] == "Test Source"


@pytest.mark.asyncio
async def test_no_entity_mentions_returns_empty_not_404(repository, temp_db_path):
    source_id = await _seed_article(repository, "No entities extracted yet", "https://example.com/b1")

    with patch.object(knowledge_graph, "_resolve_db_path", return_value=temp_db_path):
        response = await knowledge_graph.get_related_articles(source_id)

    assert response == {
        "article_id": source_id,
        "primary_entity": None,
        "articles": [],
    }


@pytest.mark.asyncio
async def test_limit_is_respected(repository, temp_db_path):
    source_id = await _seed_article(repository, "Source article", "https://example.com/c0")
    related_ids = [
        await _seed_article(repository, f"Related {i}", f"https://example.com/c{i}")
        for i in range(1, 9)
    ]

    mentions = [(source_id, "OpenAI", "company", 0)] + [
        (rid, "OpenAI", "company", 0) for rid in related_ids
    ]
    _seed_entities(temp_db_path, mentions)

    with patch.object(knowledge_graph, "_resolve_db_path", return_value=temp_db_path):
        response = await knowledge_graph.get_related_articles(source_id, limit=3)

    assert len(response["articles"]) == 3
