from app.models import Product, SyncStatus
from app.services import product_service


def _product_form(**overrides):
    data = {
        "title": "Test Course",
        "description": "A course for testing.",
        "category": "Testing",
        "price": "19.99",
        "level": "Beginner",
    }
    data.update(overrides)
    return data


def test_create_product_dual_write_success(monkeypatch, admin_client, db_session):
    monkeypatch.setattr(product_service.vector_store, "upsert_product", lambda *a, **k: None)

    resp = admin_client.post("/admin/products/new", data=_product_form())
    assert resp.status_code == 200

    product = db_session.query(Product).filter(Product.title == "Test Course").first()
    assert product is not None
    assert product.sync_status == SyncStatus.synced


def test_create_product_dual_write_failure_does_not_lose_sql_row(monkeypatch, admin_client, db_session):
    def _boom(*a, **k):
        raise RuntimeError("Mesh is down")

    monkeypatch.setattr(product_service.vector_store, "upsert_product", _boom)

    resp = admin_client.post("/admin/products/new", data=_product_form())
    assert resp.status_code == 200

    product = db_session.query(Product).filter(Product.title == "Test Course").first()
    assert product is not None  # SQL write must survive a vector store failure
    assert product.sync_status == SyncStatus.error


def test_resync_recovers_error_products(monkeypatch, admin_client, db_session):
    monkeypatch.setattr(product_service.vector_store, "upsert_product", lambda *a, **k: None)

    stale = Product(
        title="Stale Course",
        description="desc",
        category="Testing",
        price=10,
        level=None,
        sync_status=SyncStatus.error,
    )
    db_session.add(stale)
    db_session.commit()

    resp = admin_client.post("/admin/products/resync")
    assert resp.status_code == 200

    db_session.refresh(stale)
    assert stale.sync_status == SyncStatus.synced


def test_delete_product_removes_sql_row(monkeypatch, admin_client, db_session):
    monkeypatch.setattr(product_service.vector_store, "upsert_product", lambda *a, **k: None)
    monkeypatch.setattr(product_service.vector_store, "delete_product", lambda *a, **k: None)

    product = product_service.create_product(db_session, "Delete Me", "desc", "Testing", 5, None)
    product_id = product.id

    resp = admin_client.post(f"/admin/products/{product_id}/delete")
    assert resp.status_code == 200

    db_session.expire_all()  # the delete happened in a different request-scoped session
    assert db_session.get(Product, product_id) is None
