from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, SESSION_MAX_AGE, create_session_token, hash_password, verify_password
from app.database import get_db
from app.templating import templates
from app.deps import get_current_user
from app.models import User, UserRole

router = APIRouter()

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "register.html", {"error": None})


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            request, "register.html", {"error": "An account with that email already exists."}, status_code=400
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            request, "register.html", {"error": "Password must be at least 6 characters."}, status_code=400
        )

    user = User(email=email, password_hash=hash_password(password), role=UserRole.user)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session_token(user.id, user.role.value)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return response


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid email or password."}, status_code=400
        )

    token = create_session_token(user.id, user.role.value)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return response


@router.post("/logout")
@router.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
