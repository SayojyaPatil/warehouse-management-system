# Warehouse Management System

Backend platform for warehouse operations: inventory tracking, velocity-based SKU slotting, and order fulfillment. Built with FastAPI, SQLAlchemy, and PostgreSQL, containerized with Docker.

## Features

**Inventory tracking**
- Receive stock into bin locations with per-location capacity enforcement
- Transfer stock between locations with atomic source/destination updates
- Append-only stock movement audit trail (receive / transfer / pick / adjust)
- Low-stock report against per-product reorder points

**SKU slotting**
- Velocity-class policy: fast movers (class A) slot into zone A nearest dispatch, B into B, C into C
- `/slotting/recommendations` reports every mis-slotted inventory row and suggests the best-fit location in the correct zone with spare capacity

**Order fulfillment**
- Order intake with multi-line orders
- Allocation walks pick faces zone A first, consuming availability claimed by earlier lines; partial allocation keeps the order pending
- Pick list generation sorted in warehouse walk order (zone, then location)
- Shipping decrements inventory, records pick movements, and rejects stale allocations if stock moved after allocation (409)

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 · PostgreSQL 16 · Docker Compose · PyTest

## Quick start

```bash
docker compose up --build
```

API at http://localhost:8000, interactive docs at http://localhost:8000/docs.

Seed demo data (10 products, 36 bin locations, scattered stock):

```bash
docker compose exec api python -m scripts.seed_data
```

Run the scheduled reorder report:

```bash
docker compose exec api python -m scripts.low_stock_report
```

## Local development

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://warehouse:warehouse@localhost:5432/warehouse
uvicorn app.main:app --reload
```

## Tests

End-to-end API tests run against in-memory SQLite, no database service required:

```bash
python -m pytest tests/ -v
```

Covers: capacity enforcement, transfers, low-stock detection, slotting recommendations, the full order → allocate → pick → ship flow, partial allocation, and stale-allocation rejection.

## Schema

```
products         sku, name, category, unit_cost, velocity_class, reorder_point, reorder_qty
locations        code (Z-AA-RR-BB), zone, aisle, rack, bin, capacity
inventory        (product, location) -> quantity          [unique pair]
orders           order_number, status: pending|allocated|shipped|cancelled
order_lines      order, product, quantity, allocated_qty
pick_tasks       order_line, location, quantity           [the pick list]
stock_movements  product, from/to location, qty, type, reference, timestamp
```

## API overview

| Method | Path | Purpose |
|---|---|---|
| POST | /products | Create SKU |
| POST | /locations | Create bin location |
| POST | /inventory/receive | Receive stock (capacity-checked) |
| POST | /inventory/transfer | Move stock between bins |
| GET | /inventory | Stock on hand, filterable by SKU/zone |
| GET | /inventory/low-stock | Products at/below reorder point |
| GET | /slotting/recommendations | Mis-slotted stock + suggested moves |
| POST | /orders | Create order |
| POST | /orders/{id}/allocate | Allocate stock, build pick tasks |
| GET | /orders/{id}/picklist | Pick list in walk order |
| POST | /orders/{id}/ship | Ship, decrement stock, audit movements |
