from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.deps import get_current_user
from app.models import Product, User

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_current_user)):
    featured = db.query(Product).order_by(Product.created_at.desc()).limit(6).all()
    return templates.TemplateResponse(
        request, "home.html", {"current_user": user, "featured": featured}
    )


@router.get("/products", response_class=HTMLResponse)
def products_page(
    request: Request,
    q: str = "",
    category: str = "",
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    query = db.query(Product)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Product.title.ilike(like), Product.description.ilike(like)))
    if category:
        query = query.filter(Product.category == category)
    products = query.order_by(Product.created_at.desc()).all()
    categories = [c[0] for c in db.query(Product.category).distinct().order_by(Product.category)]
    return templates.TemplateResponse(
        request,
        "products.html",
        {
            "current_user": user,
            "products": products,
            "q": q,
            "active_category": category,
            "categories": categories,
        },
    )


@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail_page(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if not product:
        return RedirectResponse("/products", status_code=303)
    related = (
        db.query(Product)
        .filter(Product.category == product.category, Product.id != product.id)
        .limit(3)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "product_detail.html",
        {"current_user": user, "product": product, "related": related},
    )
