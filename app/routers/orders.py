"""Order fulfillment: order intake, stock allocation, pick lists, shipping.

Allocation strategy: for each order line, walk inventory for that product
zone A first (pick faces nearest dispatch), largest quantity first within a
zone, consuming availability that earlier lines in the same order already
claimed. Partial allocation is allowed; the order only moves to ALLOCATED
when every line is fully covered.
"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/orders", tags=["orders"])


def _get_order(db: Session, order_id: int) -> models.Order:
    order = db.query(models.Order).filter_by(id=order_id).first()
    if not order:
        raise HTTPException(404, f"Order {order_id} not found")
    return order


def _order_out(order: models.Order) -> schemas.OrderOut:
    return schemas.OrderOut(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        created_at=order.created_at,
        lines=[
            schemas.OrderLineOut(
                sku=line.product.sku,
                quantity=line.quantity,
                allocated_qty=line.allocated_qty,
            )
            for line in order.lines
        ],
    )


@router.post("", response_model=schemas.OrderOut, status_code=201)
def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    if db.query(models.Order).filter_by(order_number=payload.order_number).first():
        raise HTTPException(409, f"Order '{payload.order_number}' already exists")

    order = models.Order(order_number=payload.order_number)
    for line in payload.lines:
        product = db.query(models.Product).filter_by(sku=line.sku).first()
        if not product:
            raise HTTPException(404, f"SKU '{line.sku}' not found")
        order.lines.append(models.OrderLine(product_id=product.id, quantity=line.quantity))

    db.add(order)
    db.commit()
    db.refresh(order)
    return _order_out(order)


@router.get("/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return _order_out(_get_order(db, order_id))


@router.post("/{order_id}/allocate", response_model=schemas.OrderOut)
def allocate_order(order_id: int, db: Session = Depends(get_db)):
    order = _get_order(db, order_id)
    if order.status != models.OrderStatus.PENDING:
        raise HTTPException(422, f"Order is '{order.status.value}', only pending orders can be allocated")

    # availability claimed by earlier lines in this same allocation pass
    claimed: dict[int, int] = defaultdict(int)  # inventory row id -> qty claimed

    fully_allocated = True
    for line in order.lines:
        # reset any previous partial allocation
        line.allocated_qty = 0
        line.pick_tasks.clear()

        rows = (
            db.query(models.Inventory)
            .join(models.Location)
            .filter(models.Inventory.product_id == line.product_id)
            .order_by(models.Location.zone.asc(), models.Inventory.quantity.desc())
            .all()
        )
        remaining = line.quantity
        for row in rows:
            if remaining == 0:
                break
            available = row.quantity - claimed[row.id]
            if available <= 0:
                continue
            take = min(available, remaining)
            claimed[row.id] += take
            remaining -= take
            line.allocated_qty += take
            line.pick_tasks.append(
                models.PickTask(location_id=row.location_id, quantity=take)
            )
        if remaining > 0:
            fully_allocated = False

    if fully_allocated:
        order.status = models.OrderStatus.ALLOCATED
    db.commit()
    db.refresh(order)
    return _order_out(order)


@router.get("/{order_id}/picklist", response_model=list[schemas.PickTaskOut])
def get_picklist(order_id: int, db: Session = Depends(get_db)):
    order = _get_order(db, order_id)
    tasks: list[schemas.PickTaskOut] = []
    for line in order.lines:
        for task in line.pick_tasks:
            tasks.append(
                schemas.PickTaskOut(
                    sku=line.product.sku,
                    product_name=line.product.name,
                    location_code=task.location.code,
                    zone=task.location.zone,
                    quantity=task.quantity,
                )
            )
    # walk order: zone, then location code
    tasks.sort(key=lambda t: (t.zone, t.location_code))
    return tasks


@router.post("/{order_id}/ship", response_model=schemas.OrderOut)
def ship_order(order_id: int, db: Session = Depends(get_db)):
    order = _get_order(db, order_id)
    if order.status != models.OrderStatus.ALLOCATED:
        raise HTTPException(422, f"Order is '{order.status.value}', only allocated orders can ship")

    for line in order.lines:
        for task in line.pick_tasks:
            row = (
                db.query(models.Inventory)
                .filter_by(product_id=line.product_id, location_id=task.location_id)
                .first()
            )
            if row is None or row.quantity < task.quantity:
                raise HTTPException(
                    409,
                    f"Stock for {line.product.sku} at {task.location.code} changed since allocation; re-allocate",
                )
            row.quantity -= task.quantity
            if row.quantity == 0:
                db.delete(row)
            db.add(
                models.StockMovement(
                    product_id=line.product_id,
                    from_location_id=task.location_id,
                    quantity=task.quantity,
                    movement_type=models.MovementType.PICK,
                    reference=order.order_number,
                )
            )

    order.status = models.OrderStatus.SHIPPED
    db.commit()
    db.refresh(order)
    return _order_out(order)
