"""Inventory tracking: receiving, transfers, stock queries, low-stock alerts."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _get_product(db: Session, sku: str) -> models.Product:
    product = db.query(models.Product).filter_by(sku=sku).first()
    if not product:
        raise HTTPException(404, f"SKU '{sku}' not found")
    return product


def _get_location(db: Session, code: str) -> models.Location:
    location = db.query(models.Location).filter_by(code=code).first()
    if not location:
        raise HTTPException(404, f"Location '{code}' not found")
    return location


def _location_load(db: Session, location_id: int) -> int:
    return (
        db.query(func.coalesce(func.sum(models.Inventory.quantity), 0))
        .filter(models.Inventory.location_id == location_id)
        .scalar()
    )


def _check_capacity(db: Session, location: models.Location, incoming: int) -> None:
    load = _location_load(db, location.id)
    if load + incoming > location.capacity:
        raise HTTPException(
            422,
            f"Location '{location.code}' capacity exceeded: "
            f"{load}/{location.capacity} used, cannot add {incoming}",
        )


def _adjust(db: Session, product_id: int, location_id: int, delta: int) -> None:
    row = (
        db.query(models.Inventory)
        .filter_by(product_id=product_id, location_id=location_id)
        .first()
    )
    if row is None:
        row = models.Inventory(product_id=product_id, location_id=location_id, quantity=0)
        db.add(row)
    row.quantity += delta
    if row.quantity < 0:
        raise HTTPException(422, "Insufficient stock for this operation")
    if row.quantity == 0:
        db.delete(row)


@router.post("/receive", status_code=201)
def receive_stock(payload: schemas.ReceiveStock, db: Session = Depends(get_db)):
    product = _get_product(db, payload.sku)
    location = _get_location(db, payload.location_code)
    _check_capacity(db, location, payload.quantity)
    _adjust(db, product.id, location.id, payload.quantity)
    db.add(
        models.StockMovement(
            product_id=product.id,
            to_location_id=location.id,
            quantity=payload.quantity,
            movement_type=models.MovementType.RECEIVE,
            reference=payload.reference,
        )
    )
    db.commit()
    return {"detail": f"Received {payload.quantity} x {payload.sku} into {location.code}"}


@router.post("/transfer", status_code=201)
def transfer_stock(payload: schemas.TransferStock, db: Session = Depends(get_db)):
    product = _get_product(db, payload.sku)
    src = _get_location(db, payload.from_location)
    dst = _get_location(db, payload.to_location)
    if src.id == dst.id:
        raise HTTPException(422, "Source and destination are the same location")

    on_hand = (
        db.query(models.Inventory)
        .filter_by(product_id=product.id, location_id=src.id)
        .first()
    )
    if on_hand is None or on_hand.quantity < payload.quantity:
        raise HTTPException(422, f"Insufficient stock of {payload.sku} at {src.code}")

    _check_capacity(db, dst, payload.quantity)
    _adjust(db, product.id, src.id, -payload.quantity)
    _adjust(db, product.id, dst.id, payload.quantity)
    db.add(
        models.StockMovement(
            product_id=product.id,
            from_location_id=src.id,
            to_location_id=dst.id,
            quantity=payload.quantity,
            movement_type=models.MovementType.TRANSFER,
        )
    )
    db.commit()
    return {"detail": f"Transferred {payload.quantity} x {payload.sku}: {src.code} -> {dst.code}"}


@router.get("", response_model=list[schemas.InventoryOut])
def list_inventory(sku: str | None = None, zone: str | None = None, db: Session = Depends(get_db)):
    query = (
        db.query(models.Inventory)
        .join(models.Product)
        .join(models.Location)
        .order_by(models.Location.code)
    )
    if sku:
        query = query.filter(models.Product.sku == sku)
    if zone:
        query = query.filter(models.Location.zone == zone)
    return [
        schemas.InventoryOut(
            sku=row.product.sku,
            product_name=row.product.name,
            location_code=row.location.code,
            zone=row.location.zone,
            quantity=row.quantity,
        )
        for row in query.all()
    ]


@router.get("/low-stock", response_model=list[schemas.LowStockOut])
def low_stock(db: Session = Depends(get_db)):
    """Products whose total on-hand quantity is at or below their reorder point."""
    totals = (
        db.query(
            models.Product,
            func.coalesce(func.sum(models.Inventory.quantity), 0).label("total"),
        )
        .outerjoin(models.Inventory)
        .group_by(models.Product.id)
        .all()
    )
    return [
        schemas.LowStockOut(
            sku=product.sku,
            product_name=product.name,
            total_quantity=total,
            reorder_point=product.reorder_point,
            suggested_reorder_qty=product.reorder_qty,
        )
        for product, total in totals
        if product.reorder_point > 0 and total <= product.reorder_point
    ]
