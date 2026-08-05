from app.models import User


def test_register_creates_user_and_logs_in(client, db_session):
    resp = client.post("/register", data={"email": "new@test.local", "password": "password123"})
    assert resp.status_code == 200
    assert "smartreco_session" in client.cookies

    user = db_session.query(User).filter(User.email == "new@test.local").first()
    assert user is not None
    assert user.password_hash != "password123"  # never stored in plaintext


def test_register_duplicate_email_rejected(client, regular_user):
    resp = client.post("/register", data={"email": regular_user.email, "password": "password123"})
    assert resp.status_code == 400
    assert "already exists" in resp.text


def test_register_short_password_rejected(client):
    resp = client.post("/register", data={"email": "short@test.local", "password": "ab"})
    assert resp.status_code == 400


def test_login_wrong_password_rejected(client, regular_user):
    resp = client.post("/login", data={"email": regular_user.email, "password": "wrong-password"})
    assert resp.status_code == 400
    assert "smartreco_session" not in client.cookies


def test_login_correct_password_succeeds(client, regular_user):
    resp = client.post("/login", data={"email": regular_user.email, "password": "password123"})
    assert resp.status_code == 200
    assert "smartreco_session" in client.cookies


def test_logout_clears_session(logged_in_client):
    resp = logged_in_client.get("/logout")
    assert resp.status_code == 200
    # a subsequent admin-only request should now be unauthenticated
    resp2 = logged_in_client.get("/admin/products")
    assert resp2.status_code == 401


def test_non_admin_cannot_access_admin_routes(logged_in_client):
    resp = logged_in_client.get("/admin/products")
    assert resp.status_code == 403


def test_admin_can_access_admin_routes(admin_client):
    resp = admin_client.get("/admin/products")
    assert resp.status_code == 200
