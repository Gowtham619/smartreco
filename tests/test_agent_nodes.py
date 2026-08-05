import json

from app.agent import nodes
from app.models import Event, Product
from app.services import vector_store


def _make_product(db, **overrides):
    data = dict(title="Agentic AI Foundations", description="desc", category="Agentic AI", price=49, level="Beginner")
    data.update(overrides)
    p = Product(**data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_analyze_activity_weights_product_views_into_category_filter(db_session, regular_user):
    product = _make_product(db_session)
    db_session.add(Event(user_id=regular_user.id, event_type="product_view", product_id=product.id))
    db_session.add(Event(user_id=regular_user.id, event_type="click", product_id=product.id))
    db_session.add(Event(user_id=regular_user.id, event_type="search", query="agentic ai"))
    db_session.commit()

    result = nodes.analyze_activity({"db": db_session, "user_id": regular_user.id})

    assert result["category_filter"] == "Agentic AI"
    assert "agentic ai" in result["interest_profile"]["search_terms"]
    assert product.title in result["interest_profile"]["viewed_titles"]
    assert result["retry_count"] == 0


def test_analyze_activity_with_no_events_falls_back_gracefully(db_session, regular_user):
    result = nodes.analyze_activity({"db": db_session, "user_id": regular_user.id})

    assert result["category_filter"] is None
    assert result["query_text"] == "popular courses for a new learner"


def test_retrieve_handles_vector_store_failure_gracefully(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("mesh down")

    monkeypatch.setattr(vector_store, "query", _boom)

    result = nodes.retrieve({"query_text": "agentic ai", "retry_count": 0, "category_filter": "Agentic AI"})
    assert result["candidates"] == []


def test_evaluate_retrieval_retries_once_when_thin_and_filtered():
    state = {"candidates": [{"product_id": 1}], "retry_count": 0, "category_filter": "Agentic AI"}
    result = nodes.evaluate_retrieval(state)
    assert result == {"needs_retry": True, "retry_count": 1}


def test_evaluate_retrieval_does_not_retry_twice():
    state = {"candidates": [{"product_id": 1}], "retry_count": 1, "category_filter": "Agentic AI"}
    result = nodes.evaluate_retrieval(state)
    assert result == {"needs_retry": False}


def test_evaluate_retrieval_proceeds_when_enough_candidates():
    state = {
        "candidates": [{"product_id": i} for i in range(5)],
        "retry_count": 0,
        "category_filter": "Agentic AI",
    }
    result = nodes.evaluate_retrieval(state)
    assert result == {"needs_retry": False}


def test_route_after_evaluate_matches_needs_retry_flag():
    assert nodes.route_after_evaluate({"needs_retry": True}) == "retrieve"
    assert nodes.route_after_evaluate({"needs_retry": False}) == "generate"


def test_generate_returns_default_narrative_with_no_candidates(db_session):
    result = nodes.generate({"db": db_session, "candidates": []})
    assert result["picks"] == []
    assert "explore" in result["narrative"].lower() or "search" in result["narrative"].lower()


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeChatModel:
    def __init__(self, content):
        self._content = content

    def invoke(self, *a, **k):
        return _FakeResponse(self._content)


def test_generate_drops_hallucinated_product_ids(monkeypatch, db_session):
    real = _make_product(db_session, title="Real Course")
    fake_llm_content = json.dumps(
        {
            "narrative": "Great picks for you.",
            "picks": [
                {"product_id": real.id, "reason": "matches your interest"},
                {"product_id": 999999, "reason": "hallucinated, not a real candidate"},
            ],
        }
    )
    monkeypatch.setattr(nodes, "get_chat_model", lambda: _FakeChatModel(fake_llm_content))

    state = {
        "db": db_session,
        "candidates": [{"product_id": real.id}],
        "interest_profile": {"summary": "likes real courses"},
    }
    result = nodes.generate(state)

    assert len(result["picks"]) == 1
    assert result["picks"][0]["product_id"] == real.id


def test_generate_falls_back_when_llm_raises(monkeypatch, db_session):
    real = _make_product(db_session, title="Fallback Course")

    class _BoomModel:
        def invoke(self, *a, **k):
            raise RuntimeError("mesh outage")

    monkeypatch.setattr(nodes, "get_chat_model", lambda: _BoomModel())

    state = {
        "db": db_session,
        "candidates": [{"product_id": real.id}],
        "interest_profile": {"summary": "likes real courses"},
    }
    result = nodes.generate(state)

    assert result["narrative"]  # non-empty fallback text
    assert result["picks"] == [{"product_id": real.id, "reason": None}]
