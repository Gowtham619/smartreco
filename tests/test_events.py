import json

from app.models import Event
from app.services import recommendation_service


def test_anonymous_batch_is_accepted_but_not_stored(client, db_session):
    resp = client.post("/api/events/batch", json={"events": [{"event_type": "page_view"}]})
    assert resp.status_code == 202
    assert db_session.query(Event).count() == 0


def test_logged_in_batch_inserts_events(monkeypatch, logged_in_client, db_session, regular_user):
    # background trigger check shouldn't need to run for this assertion; keep it inert.
    monkeypatch.setattr(recommendation_service, "maybe_trigger_regeneration", lambda *a, **k: None)

    payload = {
        "events": [
            {"event_type": "page_view"},
            {"event_type": "search", "query": "agentic ai"},
            {"event_type": "product_view", "product_id": 1},
        ]
    }
    resp = logged_in_client.post("/api/events/batch", json=payload)
    assert resp.status_code == 202

    events = db_session.query(Event).filter(Event.user_id == regular_user.id).all()
    assert len(events) == 3
    assert {e.event_type.value for e in events} == {"page_view", "search", "product_view"}


def test_malformed_batch_body_does_not_crash(logged_in_client):
    resp = logged_in_client.post(
        "/api/events/batch", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 202


def test_unknown_event_type_is_dropped_not_rejected(monkeypatch, logged_in_client, db_session, regular_user):
    monkeypatch.setattr(recommendation_service, "maybe_trigger_regeneration", lambda *a, **k: None)
    payload = {"events": [{"event_type": "totally_made_up"}, {"event_type": "click", "product_id": 1}]}
    resp = logged_in_client.post("/api/events/batch", json=payload)
    assert resp.status_code == 202

    events = db_session.query(Event).filter(Event.user_id == regular_user.id).all()
    assert len(events) == 1
    assert events[0].event_type.value == "click"
