"""Product catalog and location management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(tags=["catalog"])


@router.post("/products", response_model=schemas.ProductOut, status_code=201)
def create_product(payload: schemas.ProductCreate, db: Session = Depends(get_db)):
    if db.query(models.Product).filter_by(sku=payload.sku).first():
        raise HTTPException(409, f"SKU '{payload.sku}' already exists")
    product = models.Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/products", response_model=list[schemas.ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(models.Product).order_by(models.Product.sku).all()


@router.get("/products/{sku}", response_model=schemas.ProductOut)
def get_product(sku: str, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter_by(sku=sku).first()
    if not product:
        raise HTTPException(404, f"SKU '{sku}' not found")
    return product


@router.post("/locations", response_model=schemas.LocationOut, status_code=201)
def create_location(payload: schemas.LocationCreate, db: Session = Depends(get_db)):
    code = f"{payload.zone}-{payload.aisle:02d}-{payload.rack:02d}-{payload.bin:02d}"
    if db.query(models.Location).filter_by(code=code).first():
        raise HTTPException(409, f"Location '{code}' already exists")
    location = models.Location(code=code, **payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/locations", response_model=list[schemas.LocationOut])
def list_locations(zone: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Location)
    if zone:
        query = query.filter_by(zone=zone)
    return query.order_by(models.Location.code).all()
