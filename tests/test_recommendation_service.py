from datetime import datetime, timedelta

from app.models import Recommendation, RecommendationState
from app.services import event_service, recommendation_service


class FakeGraph:
    def __init__(self, result=None, exc=None):
        self._result = result or {"narrative": "Fake narrative", "picks": []}
        self._exc = exc
        self.invocations = 0

    def invoke(self, state, config=None):
        self.invocations += 1
        if self._exc:
            raise self._exc
        return self._result


def _add_events(db, user_id, count):
    from app.models import Event

    for _ in range(count):
        db.add(Event(user_id=user_id, event_type="page_view"))
    db.commit()


def test_maybe_trigger_skips_below_first_threshold(monkeypatch, db_session, regular_user):
    fake = FakeGraph()
    monkeypatch.setattr(recommendation_service, "build_graph", lambda: fake)

    _add_events(db_session, regular_user.id, 2)  # first-time threshold is 3
    recommendation_service.maybe_trigger_regeneration(regular_user.id)

    assert fake.invocations == 0
    assert db_session.query(Recommendation).count() == 0


def test_maybe_trigger_fires_at_first_threshold(monkeypatch, db_session, regular_user):
    fake = FakeGraph()
    monkeypatch.setattr(recommendation_service, "build_graph", lambda: fake)

    _add_events(db_session, regular_user.id, 3)
    recommendation_service.maybe_trigger_regeneration(regular_user.id)

    assert fake.invocations == 1
    assert db_session.query(Recommendation).count() == 1


def test_cooldown_blocks_immediate_retrigger(monkeypatch, db_session, regular_user):
    fake = FakeGraph()
    monkeypatch.setattr(recommendation_service, "build_graph", lambda: fake)

    _add_events(db_session, regular_user.id, 3)
    recommendation_service.maybe_trigger_regeneration(regular_user.id)
    assert fake.invocations == 1

    # more events arrive immediately after, well within the cooldown window
    _add_events(db_session, regular_user.id, 10)
    recommendation_service.maybe_trigger_regeneration(regular_user.id)
    assert fake.invocations == 1  # still just the one — cooldown held


def test_generating_flag_prevents_concurrent_run(monkeypatch, db_session, regular_user):
    fake = FakeGraph()
    monkeypatch.setattr(recommendation_service, "build_graph", lambda: fake)

    state = recommendation_service.get_or_create_state(db_session, regular_user.id)
    state.generating = True
    db_session.commit()

    _add_events(db_session, regular_user.id, 5)
    recommendation_service.maybe_trigger_regeneration(regular_user.id)

    assert fake.invocations == 0


def test_generation_failure_resets_generating_flag(monkeypatch, db_session, regular_user):
    fake = FakeGraph(exc=RuntimeError("mesh exploded"))
    monkeypatch.setattr(recommendation_service, "build_graph", lambda: fake)

    _add_events(db_session, regular_user.id, 3)
    recommendation_service.maybe_trigger_regeneration(regular_user.id)  # must not raise

    state = db_session.get(RecommendationState, regular_user.id)
    assert state.generating is False
    assert db_session.query(Recommendation).count() == 0


def test_ensure_recommendation_creates_on_first_visit(monkeypatch, db_session, regular_user):
    fake = FakeGraph(result={"narrative": "Welcome!", "picks": []})
    monkeypatch.setattr(recommendation_service, "build_graph", lambda: fake)

    rec = recommendation_service.ensure_recommendation(db_session, regular_user.id)
    assert rec is not None
    assert rec.narrative == "Welcome!"

    # second call should serve the cached row, not regenerate
    rec2 = recommendation_service.ensure_recommendation(db_session, regular_user.id)
    assert rec2.id == rec.id
    assert fake.invocations == 1
