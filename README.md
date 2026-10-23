# Warehouse Management System

**Inventory control · Velocity-based SKU slotting · Order fulfillment · Stock movement auditing**

A backend warehouse management application built with **Python, FastAPI, SQLAlchemy, and PostgreSQL**. It models everyday warehouse operations, from receiving inventory into capacity-limited bin locations through allocating and shipping customer orders, with an auditable record of stock movements.

The project uses **Docker Compose** for local setup and **pytest** for API-level testing.

## Features

### Inventory management

- Receive stock into bin locations while enforcing location capacity.
- Transfer stock between locations with atomic updates to source and destination inventory.
- Record receive, transfer, pick, and adjustment events in an append-only stock-movement history.
- Query inventory by SKU or zone and identify products at or below their reorder points.

### Velocity-based slotting

- Categorize products by movement class: **A** (fast-moving), **B**, or **C**.
- Recommend locations in the appropriate zone that have available capacity.
- Identify mis-slotted inventory through `GET /slotting/recommendations`.

### Order fulfillment

- Create multi-line customer orders.
- Allocate stock to order lines, prioritizing Zone A picking faces.
- Generate pick tasks ordered by zone and location for a warehouse-friendly pick sequence.
- Support partially allocated orders, which remain pending until stock can be allocated.
- Validate allocations at shipping time and return **HTTP 409 Conflict** if inventory changed after allocation.

## Architecture

```mermaid
flowchart TD
    Client[API Client / Swagger UI]
    API[FastAPI REST API]
    Logic[Inventory, Slotting and Fulfillment Logic]
    DB[(PostgreSQL Database)]
    Audit[Stock Movement Audit Records]
    Client --> API --> Logic --> DB
    Logic --> Audit --> DB
```

The application exposes REST endpoints through FastAPI. Business operations update warehouse data stored in PostgreSQL through SQLAlchemy. Inventory-changing operations also record stock movements for traceability.

### Order lifecycle

```mermaid
flowchart LR
    A[Create order] --> B[Allocate inventory]
    B --> C{Enough stock?}
    C -->|Yes| D[Generate pick list]
    C -->|No| E[Remain pending]
    E --> B
    D --> F{Allocation still valid?}
    F -->|Yes| G[Ship order]
    F -->|No| H[409 Conflict]
    G --> I[Update inventory and audit movements]
```

## Technology stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.12 |
| API framework | FastAPI |
| ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL 16 |
| Local orchestration | Docker Compose |
| Tests | pytest (in-memory SQLite for API tests) |

## Getting started

### Prerequisites

- Docker and Docker Compose (recommended)
- Alternatively, Python 3.12 and a running PostgreSQL instance

### Run with Docker

```bash
git clone https://github.com/SayojyaPatil/warehouse-management-system.git
cd warehouse-management-system
docker compose up --build
```

Once the containers are running:

- **API:** http://localhost:8000
- **Interactive API documentation:** http://localhost:8000/docs

### Seed sample warehouse data

```bash
docker compose exec api python -m scripts.seed_data
```

The seed script populates example products and bin locations, including **10 products and 36 locations**, to make exploration easier.

### Generate the low-stock report

```bash
docker compose exec api python -m scripts.low_stock_report
```

### Run locally without Docker

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start PostgreSQL, then configure your connection and launch the API:

```bash
export DATABASE_URL=postgresql://warehouse:warehouse@localhost:5432/warehouse
uvicorn app.main:app --reload
```

The database, user, and credentials in the example URL must match your local PostgreSQL setup. See `.env.example` for the repository's configuration template.

## API reference

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/products` | Create a product/SKU |
| `POST` | `/locations` | Create a warehouse bin location |
| `POST` | `/inventory/receive` | Receive inventory with capacity checks |
| `POST` | `/inventory/transfer` | Transfer inventory between locations |
| `GET` | `/inventory` | List stock, optionally filtered by SKU or zone |
| `GET` | `/inventory/low-stock` | List products at/below their reorder points |
| `GET` | `/slotting/recommendations` | Find mis-slotted stock and suggested locations |
| `POST` | `/orders` | Create an order with multiple lines |
| `POST` | `/orders/{id}/allocate` | Allocate available stock and create pick tasks |
| `GET` | `/orders/{id}/picklist` | Retrieve the pick list in warehouse walk order |
| `POST` | `/orders/{id}/ship` | Ship an order, decrement inventory and record movements |

For request/response schemas and a live API playground, open **`/docs`** after starting the application. The schemas there are the authoritative reference for request fields.

## Data model

| Entity | Purpose | Notable fields |
| --- | --- | --- |
| `products` | Product master | SKU, category, cost, velocity class, reorder settings |
| `locations` | Storage bin master | Location code, zone, aisle, rack, bin, capacity |
| `inventory` | Quantity per SKU/location | Product, location, quantity (unique product/location pair) |
| `orders` | Customer order state | Order number, status |
| `order_lines` | Requested and allocated units | Product, quantity, allocated quantity |
| `pick_tasks` | Picking instructions | Order line, location, quantity |
| `stock_movements` | Inventory audit history | Product, origin/destination, quantity, type, reference, time |

Supported order states include `pending`, `allocated`, `shipped`, and `cancelled`.

## Testing

Run the automated tests with:

```bash
python -m pytest tests/ -v
```

The API tests use **in-memory SQLite**, so a PostgreSQL service is not required to execute the test suite. The documented test coverage includes:

- Bin capacity enforcement and inventory transfers
- Reorder-point checks and slotting recommendations
- Order creation, allocation, picking and shipping
- Partial allocation handling
- Rejection of stale shipping allocations

**Note:** Tests should be run locally or in CI before claiming a passing test count or test coverage percentage.

## Engineering highlights

- **Inventory integrity:** atomic transfer updates help prevent discrepancies between source and destination locations.
- **Allocation correctness:** existing claims are considered during order allocation, and changes to stock are checked again before shipping.
- **Warehouse-aware fulfillment:** picking is organized in zone/location order rather than arbitrary database order.
- **Traceability:** stock movements provide an audit trail for physical inventory changes.
- **Reproducibility:** containerized services, a seed script, and automated API tests make the project easier to evaluate.

## Scope and next steps

This repository presents a **backend implementation**, not a complete commercial WMS. Possible future extensions include authentication and role-based permissions, barcode-scanning workflows, replenishment tasks, richer inventory reservation policies, observability, and CI validation.

## Author

[Sayojya Patil](https://github.com/SayojyaPatil)
