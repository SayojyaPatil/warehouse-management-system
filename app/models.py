"""Normalized warehouse schema.

Product        — catalog entry keyed by SKU, with velocity class for slotting.
Location       — physical bin: zone/aisle/rack/bin with a capacity limit.
Inventory      — quantity of one product at one location (unique pair).
Order/OrderLine — customer demand.
PickTask       — allocation of an order line to a location (the pick list).
StockMovement  — append-only audit trail of every stock change.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VelocityClass(str, enum.Enum):
    A = "A"  # fast mover — slot in zone A (nearest dispatch)
    B = "B"
    C = "C"  # slow mover


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    ALLOCATED = "allocated"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class MovementType(str, enum.Enum):
    RECEIVE = "receive"
    TRANSFER = "transfer"
    PICK = "pick"
    ADJUST = "adjust"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    sku = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, default="general")
    unit_cost = Column(Float, nullable=False, default=0.0)
    velocity_class = Column(Enum(VelocityClass), nullable=False, default=VelocityClass.C)
    reorder_point = Column(Integer, nullable=False, default=0)
    reorder_qty = Column(Integer, nullable=False, default=0)

    inventory = relationship("Inventory", back_populates="product")


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, index=True, nullable=False)  # e.g. A-01-02-03
    zone = Column(String(8), nullable=False, index=True)
    aisle = Column(Integer, nullable=False)
    rack = Column(Integer, nullable=False)
    bin = Column(Integer, nullable=False)
    capacity = Column(Integer, nullable=False, default=100)

    inventory = relationship("Inventory", back_populates="location")

    __table_args__ = (UniqueConstraint("zone", "aisle", "rack", "bin", name="uq_location_position"),)


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)

    product = relationship("Product", back_populates="inventory")
    location = relationship("Location", back_populates="inventory")

    __table_args__ = (UniqueConstraint("product_id", "location_id", name="uq_product_location"),)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    order_number = Column(String(64), unique=True, index=True, nullable=False)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    lines = relationship("OrderLine", back_populates="order", cascade="all, delete-orphan")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    allocated_qty = Column(Integer, nullable=False, default=0)

    order = relationship("Order", back_populates="lines")
    product = relationship("Product")
    pick_tasks = relationship("PickTask", back_populates="order_line", cascade="all, delete-orphan")


class PickTask(Base):
    __tablename__ = "pick_tasks"

    id = Column(Integer, primary_key=True)
    order_line_id = Column(Integer, ForeignKey("order_lines.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    quantity = Column(Integer, nullable=False)

    order_line = relationship("OrderLine", back_populates="pick_tasks")
    location = relationship("Location")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    from_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    to_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    quantity = Column(Integer, nullable=False)
    movement_type = Column(Enum(MovementType), nullable=False)
    reference = Column(String(128), nullable=True)  # e.g. order number, PO number
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
