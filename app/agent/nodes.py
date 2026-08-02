import json
import logging
from collections import OrderedDict, defaultdict

from app.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from app.agent.state import AgentState
from app.models import Product
from app.services import event_service, vector_store
from app.services.mesh_client import get_chat_model

logger = logging.getLogger("smartreco.agent")

EVENT_LIMIT = 50
MIN_GOOD_CANDIDATES = 3
CATEGORY_FILTER_MIN_SCORE = 2.0

_WEIGHTS = {
    "product_view": 2.0,
    "click": 1.5,
}


def analyze_activity(state: AgentState) -> dict:
    db = state["db"]
    user_id = state["user_id"]
    events = event_service.get_recent_events(db, user_id, limit=EVENT_LIMIT)

    product_ids = {e.product_id for e in events if e.product_id}
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()} if product_ids else {}

    category_scores: dict[str, float] = defaultdict(float)
    viewed_titles: "OrderedDict[str, None]" = OrderedDict()
    search_terms: "OrderedDict[str, None]" = OrderedDict()

    for e in events:
        if e.event_type in ("product_view", "click") and e.product_id and e.product_id in products:
            product = products[e.product_id]
            category_scores[product.category] += _WEIGHTS[e.event_type]
            viewed_titles[product.title] = None
        elif e.event_type == "time_spent" and e.product_id and e.product_id in products and e.duration_ms:
            product = products[e.product_id]
            category_scores[product.category] += min(e.duration_ms / 30000.0, 3.0)
        elif e.event_type == "search" and e.query:
            search_terms[e.query] = None

    ranked_categories = sorted(category_scores.items(), key=lambda kv: kv[1], reverse=True)
    top_categories = [c for c, _score in ranked_categories[:3]]
    category_filter = None
    if ranked_categories and ranked_categories[0][1] >= CATEGORY_FILTER_MIN_SCORE:
        category_filter = ranked_categories[0][0]

    viewed_list = list(viewed_titles.keys())[:5]
    search_list = list(search_terms.keys())[:5]

    summary_parts = []
    if top_categories:
        summary_parts.append(f"Top interests: {', '.join(top_categories)}.")
    if search_list:
        summary_parts.append(f"Recently searched: {', '.join(search_list)}.")
    if viewed_list:
        summary_parts.append(f"Recently viewed: {', '.join(viewed_list)}.")
    interest_summary = " ".join(summary_parts) or "No strong signal yet — this user is just getting started."

    query_text = " ".join(top_categories + search_list + viewed_list).strip() or "popular courses for a new learner"

    return {
        "interest_profile": {
            "summary": interest_summary,
            "top_categories": top_categories,
            "search_terms": search_list,
            "viewed_titles": viewed_list,
        },
        "query_text": query_text,
        "category_filter": category_filter,
        "retry_count": 0,
    }


def retrieve(state: AgentState) -> dict:
    retry_count = state.get("retry_count", 0)
    category = None if retry_count > 0 else state.get("category_filter")
    try:
        candidates = vector_store.query(state["query_text"], top_k=10, category=category)
    except Exception:
        logger.error("Vector store retrieval failed, generation will fall back gracefully", exc_info=True)
        candidates = []
    return {"candidates": candidates}


def evaluate_retrieval(state: AgentState) -> dict:
    candidates = state.get("candidates", [])
    retry_count = state.get("retry_count", 0)
    if len(candidates) < MIN_GOOD_CANDIDATES and retry_count == 0 and state.get("category_filter"):
        return {"needs_retry": True, "retry_count": retry_count + 1}
    return {"needs_retry": False}


def route_after_evaluate(state: AgentState) -> str:
    return "retrieve" if state.get("needs_retry") else "generate"


def generate(state: AgentState) -> dict:
    db = state["db"]
    candidates = state.get("candidates", [])
    if not candidates:
        return {
            "narrative": "Explore a few courses and search for topics you're curious about — "
            "SmartReco will start tailoring recommendations as soon as it has something to go on.",
            "picks": [],
        }

    ids = [c["product_id"] for c in candidates]
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(ids)).all()}
    enriched = []
    for c in candidates:
        p = products.get(c["product_id"])
        if not p:
            continue
        enriched.append(
            {
                "product_id": p.id,
                "title": p.title,
                "description": p.description,
                "category": p.category,
                "price": float(p.price),
                "level": p.level,
            }
        )
    if not enriched:
        return {"narrative": "", "picks": []}

    user_prompt = build_user_prompt(state["interest_profile"]["summary"], enriched)
    model = get_chat_model()
    valid_ids = {e["product_id"] for e in enriched}

    try:
        response = model.invoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.content)
        narrative = parsed.get("narrative", "").strip()
        raw_picks = parsed.get("picks", [])
    except Exception:
        logger.error("Recommendation generation failed, falling back to top retrieval", exc_info=True)
        narrative = (
            "Based on what you've been exploring, here are a few courses worth a closer look."
        )
        raw_picks = [{"product_id": e["product_id"], "reason": None} for e in enriched[:5]]

    picks = []
    for item in raw_picks:
        pid = item.get("product_id")
        if pid in valid_ids:
            picks.append({"product_id": pid, "reason": item.get("reason")})
        if len(picks) >= 5:
            break

    if not picks:
        picks = [{"product_id": e["product_id"], "reason": None} for e in enriched[:5]]
    if not narrative:
        narrative = "Here's what SmartReco thinks fits where you're headed."

    return {"narrative": narrative, "picks": picks}
