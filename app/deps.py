from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, read_session_token
from app.database import get_db
from app.models import User, UserRole


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    data = read_session_token(token)
    if not data:
        return None
    return db.get(User, data["user_id"])


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
