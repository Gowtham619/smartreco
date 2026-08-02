from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.deps import require_user
from app.models import Product, User
from app.services import recommendation_service

router = APIRouter(tags=["recommendations"])

@router.get("/recommendations", response_class=HTMLResponse)
def recommendations_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    rec = recommendation_service.ensure_recommendation(db, user.id)
    items = []
    if rec:
        product_ids = [i.product_id for i in rec.items]
        products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
        for i in rec.items:
            p = products.get(i.product_id)
            if p:
                items.append({"product": p, "reason": i.reason, "rank": i.rank})
    return templates.TemplateResponse(
        request, "recommendations.html", {"current_user": user, "rec": rec, "items": items}
    )


@router.post("/recommendations/refresh")
def refresh_recommendations(user: User = Depends(require_user)):
    recommendation_service.force_refresh(user.id)
    return RedirectResponse("/recommendations", status_code=303)
