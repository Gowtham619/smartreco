import logging

from sqlalchemy.orm import Session

from app.models import Product, SyncStatus
from app.services import vector_store

logger = logging.getLogger("smartreco.product_service")


def _sync_to_vector_store(product: Product, db: Session) -> None:
    try:
        vector_store.upsert_product(
            product.id, product.title, product.description, product.category, float(product.price), product.level
        )
        product.sync_status = SyncStatus.synced
    except Exception:
        logger.error("Vector store upsert failed for product %s", product.id, exc_info=True)
        product.sync_status = SyncStatus.error
    db.commit()


def create_product(db: Session, title: str, description: str, category: str, price: float, level: str | None) -> Product:
    product = Product(
        title=title,
        description=description,
        category=category,
        price=price,
        level=level,
        sync_status=SyncStatus.pending,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    _sync_to_vector_store(product, db)
    return product


def update_product(
    db: Session, product: Product, title: str, description: str, category: str, price: float, level: str | None
) -> Product:
    product.title = title
    product.description = description
    product.category = category
    product.price = price
    product.level = level
    product.sync_status = SyncStatus.pending
    db.commit()
    db.refresh(product)
    _sync_to_vector_store(product, db)
    return product


def delete_product(db: Session, product: Product) -> None:
    product_id = product.id
    db.delete(product)
    db.commit()
    try:
        vector_store.delete_product(product_id)
    except Exception:
        logger.error("Vector store delete failed for product %s", product_id, exc_info=True)


def resync_products(db: Session) -> dict:
    stale = db.query(Product).filter(Product.sync_status != SyncStatus.synced).all()
    resynced, failed = 0, 0
    for product in stale:
        _sync_to_vector_store(product, db)
        if product.sync_status == SyncStatus.synced:
            resynced += 1
        else:
            failed += 1
    return {"resynced": resynced, "failed": failed, "checked": len(stale)}
