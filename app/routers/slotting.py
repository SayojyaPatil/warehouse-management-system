"""SKU slotting: velocity-based placement recommendations.

Policy: class-based slotting. Fast movers (velocity class A) belong in zone A
(closest to dispatch), B in zone B, C in zone C. The endpoint reports every
inventory row sitting in the wrong zone and suggests the emptiest location
in the correct zone with enough spare capacity to hold it.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/slotting", tags=["slotting"])


def _spare_capacity(db: Session, location: models.Location) -> int:
    used = (
        db.query(func.coalesce(func.sum(models.Inventory.quantity), 0))
        .filter(models.Inventory.location_id == location.id)
        .scalar()
    )
    return location.capacity - used


@router.get("/recommendations", response_model=list[schemas.SlottingRecommendation])
def slotting_recommendations(db: Session = Depends(get_db)):
    rows = (
        db.query(models.Inventory)
        .join(models.Product)
        .join(models.Location)
        .filter(models.Product.velocity_class != models.Location.zone)
        .order_by(models.Product.velocity_class, models.Product.sku)
        .all()
    )

    recommendations: list[schemas.SlottingRecommendation] = []
    for row in rows:
        target_zone = row.product.velocity_class.value
        candidates = (
            db.query(models.Location)
            .filter(models.Location.zone == target_zone)
            .all()
        )
        # pick the candidate with the most spare capacity that can fit the stock
        best = None
        best_spare = -1
        for loc in candidates:
            spare = _spare_capacity(db, loc)
            if spare >= row.quantity and spare > best_spare:
                best, best_spare = loc, spare

        recommendations.append(
            schemas.SlottingRecommendation(
                sku=row.product.sku,
                velocity_class=row.product.velocity_class,
                current_location=row.location.code,
                current_zone=row.location.zone,
                target_zone=target_zone,
                suggested_location=best.code if best else None,
                quantity=row.quantity,
            )
        )
    return recommendations
