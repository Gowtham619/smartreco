import bcrypt
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import settings

SESSION_COOKIE = "smartreco_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="smartreco-session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_session_token(user_id: int, role: str) -> str:
    return _serializer.dumps({"user_id": user_id, "role": role})


def read_session_token(token: str) -> dict | None:
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
