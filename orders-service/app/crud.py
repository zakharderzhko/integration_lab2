from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas


def create_order(
    db: Session,
    data: schemas.OrderCreate,
) -> models.Order:
    """Create a new order and persist it to the database with pending status."""
    order = models.Order(
        **data.model_dump(),
        predicted_price=None,
        status="pending"
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    return order


def get_order(db: Session, oid: int) -> models.Order | None:
    """Retrieve an order by its ID."""
    return db.get(models.Order, oid)


def list_orders(
    db: Session,
    limit: int = 20,
    offset: int = 0,
) -> list[models.Order]:
    """Return orders sorted by ID in descending order."""
    return list(
        db.scalars(
            select(models.Order)
            .order_by(models.Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def update_order(
    db: Session,
    order: models.Order,
    data: schemas.OrderUpdate,
) -> models.Order:
    """Update the provided fields of an existing order."""
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(order, key, value)

    db.commit()
    db.refresh(order)

    return order


def delete_order(db: Session, order: models.Order) -> None:
    """Delete an existing order from the database."""
    db.delete(order)
    db.commit()