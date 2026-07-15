"""Pydantic request/response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import MovementType, OrderStatus, VelocityClass


# ---------- Products ----------
class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str
    category: str = "general"
    unit_cost: float = 0.0
    velocity_class: VelocityClass = VelocityClass.C
    reorder_point: int = 0
    reorder_qty: int = 0


class ProductOut(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Locations ----------
class LocationCreate(BaseModel):
    zone: str = Field(min_length=1, max_length=8)
    aisle: int
    rack: int
    bin: int
    capacity: int = 100


class LocationOut(LocationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str


# ---------- Inventory ----------
class ReceiveStock(BaseModel):
    sku: str
    location_code: str
    quantity: int = Field(gt=0)
    reference: Optional[str] = None


class TransferStock(BaseModel):
    sku: str
    from_location: str
    to_location: str
    quantity: int = Field(gt=0)


class InventoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sku: str
    product_name: str
    location_code: str
    zone: str
    quantity: int


class LowStockOut(BaseModel):
    sku: str
    product_name: str
    total_quantity: int
    reorder_point: int
    suggested_reorder_qty: int


# ---------- Slotting ----------
class SlottingRecommendation(BaseModel):
    sku: str
    velocity_class: VelocityClass
    current_location: str
    current_zone: str
    target_zone: str
    suggested_location: Optional[str]
    quantity: int


# ---------- Orders ----------
class OrderLineCreate(BaseModel):
    sku: str
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    order_number: str
    lines: list[OrderLineCreate] = Field(min_length=1)


class PickTaskOut(BaseModel):
    sku: str
    product_name: str
    location_code: str
    zone: str
    quantity: int


class OrderLineOut(BaseModel):
    sku: str
    quantity: int
    allocated_qty: int


class OrderOut(BaseModel):
    id: int
    order_number: str
    status: OrderStatus
    created_at: datetime
    lines: list[OrderLineOut]


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sku: str
    movement_type: MovementType
    quantity: int
    from_location: Optional[str]
    to_location: Optional[str]
    reference: Optional[str]
    created_at: datetime
