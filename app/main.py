"""Warehouse Management System API."""
from fastapi import FastAPI

from .database import Base, engine
from .routers import catalog, inventory, orders, slotting

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Warehouse Management System",
    description=(
        "Inventory tracking, SKU slotting, and order fulfillment backend. "
        "FastAPI + SQLAlchemy + PostgreSQL."
    ),
    version="1.0.0",
)

app.include_router(catalog.router)
app.include_router(inventory.router)
app.include_router(slotting.router)
app.include_router(orders.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
