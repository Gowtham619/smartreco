from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.deps import require_admin
from app.models import Product, User
from app.services import product_service

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/products", response_class=HTMLResponse)
def list_products(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    products = db.query(Product).order_by(Product.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "admin_products.html", {"current_user": admin, "products": products}
    )


@router.get("/products/new", response_class=HTMLResponse)
def new_product_page(request: Request, admin: User = Depends(require_admin)):
    return templates.TemplateResponse(
        request, "admin_product_form.html", {"current_user": admin, "product": None, "error": None}
    )


@router.post("/products/new")
def create_product(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    price: float = Form(0),
    level: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    product_service.create_product(db, title, description, category, price, level or None)
    return RedirectResponse("/admin/products", status_code=303)


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
def edit_product_page(
    request: Request, product_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    product = db.get(Product, product_id)
    if not product:
        return RedirectResponse("/admin/products", status_code=303)
    return templates.TemplateResponse(
        request, "admin_product_form.html", {"current_user": admin, "product": product, "error": None}
    )


@router.post("/products/{product_id}/edit")
def update_product(
    request: Request,
    product_id: int,
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    price: float = Form(0),
    level: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    product = db.get(Product, product_id)
    if product:
        product_service.update_product(db, product, title, description, category, price, level or None)
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{product_id}/delete")
def delete_product(product_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    product = db.get(Product, product_id)
    if product:
        product_service.delete_product(db, product)
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/resync")
def resync_products(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    product_service.resync_products(db)
    return RedirectResponse("/admin/products", status_code=303)
