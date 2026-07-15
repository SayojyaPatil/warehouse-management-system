"""End-to-end API tests against an in-memory SQLite database."""
import os

os.environ["DATABASE_URL"] = "sqlite://"  # must be set before app imports

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.database import Base

# single shared in-memory database across sessions
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
database.engine = engine
database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


client = TestClient(app)


def make_product(sku="SKU-1", velocity="A", reorder_point=0, reorder_qty=0):
    return client.post(
        "/products",
        json={
            "sku": sku,
            "name": f"Product {sku}",
            "velocity_class": velocity,
            "reorder_point": reorder_point,
            "reorder_qty": reorder_qty,
        },
    )


def make_location(zone="A", aisle=1, rack=1, bin=1, capacity=100):
    return client.post(
        "/locations",
        json={"zone": zone, "aisle": aisle, "rack": rack, "bin": bin, "capacity": capacity},
    )


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_product_and_location_creation():
    assert make_product().status_code == 201
    assert make_product().status_code == 409  # duplicate SKU

    resp = make_location()
    assert resp.status_code == 201
    assert resp.json()["code"] == "A-01-01-01"
    assert make_location().status_code == 409  # duplicate position


def test_receive_and_capacity_limit():
    make_product()
    make_location(capacity=50)

    ok = client.post(
        "/inventory/receive",
        json={"sku": "SKU-1", "location_code": "A-01-01-01", "quantity": 40},
    )
    assert ok.status_code == 201

    too_much = client.post(
        "/inventory/receive",
        json={"sku": "SKU-1", "location_code": "A-01-01-01", "quantity": 20},
    )
    assert too_much.status_code == 422
    assert "capacity" in too_much.json()["detail"]


def test_transfer():
    make_product()
    make_location(zone="A")
    make_location(zone="B")

    client.post("/inventory/receive", json={"sku": "SKU-1", "location_code": "A-01-01-01", "quantity": 30})
    resp = client.post(
        "/inventory/transfer",
        json={"sku": "SKU-1", "from_location": "A-01-01-01", "to_location": "B-01-01-01", "quantity": 10},
    )
    assert resp.status_code == 201

    inv = client.get("/inventory", params={"sku": "SKU-1"}).json()
    by_loc = {row["location_code"]: row["quantity"] for row in inv}
    assert by_loc == {"A-01-01-01": 20, "B-01-01-01": 10}

    over = client.post(
        "/inventory/transfer",
        json={"sku": "SKU-1", "from_location": "A-01-01-01", "to_location": "B-01-01-01", "quantity": 999},
    )
    assert over.status_code == 422


def test_low_stock_report():
    make_product(sku="SKU-LOW", reorder_point=50, reorder_qty=100)
    make_product(sku="SKU-OK", reorder_point=10, reorder_qty=20)
    make_location()
    client.post("/inventory/receive", json={"sku": "SKU-LOW", "location_code": "A-01-01-01", "quantity": 30})
    client.post("/inventory/receive", json={"sku": "SKU-OK", "location_code": "A-01-01-01", "quantity": 40})

    flagged = client.get("/inventory/low-stock").json()
    assert [row["sku"] for row in flagged] == ["SKU-LOW"]
    assert flagged[0]["suggested_reorder_qty"] == 100


def test_slotting_recommendations():
    make_product(sku="SKU-FAST", velocity="A")
    make_location(zone="C")               # wrong zone for a fast mover
    make_location(zone="A", capacity=500)  # correct zone with room
    client.post("/inventory/receive", json={"sku": "SKU-FAST", "location_code": "C-01-01-01", "quantity": 60})

    recs = client.get("/slotting/recommendations").json()
    assert len(recs) == 1
    rec = recs[0]
    assert rec["sku"] == "SKU-FAST"
    assert rec["current_zone"] == "C"
    assert rec["target_zone"] == "A"
    assert rec["suggested_location"] == "A-01-01-01"


def test_full_fulfillment_flow():
    make_product(sku="SKU-1", velocity="A")
    make_location(zone="A", capacity=100)
    make_location(zone="B", capacity=100)
    client.post("/inventory/receive", json={"sku": "SKU-1", "location_code": "A-01-01-01", "quantity": 30})
    client.post("/inventory/receive", json={"sku": "SKU-1", "location_code": "B-01-01-01", "quantity": 30})

    order = client.post(
        "/orders", json={"order_number": "ORD-1", "lines": [{"sku": "SKU-1", "quantity": 40}]}
    ).json()

    allocated = client.post(f"/orders/{order['id']}/allocate").json()
    assert allocated["status"] == "allocated"
    assert allocated["lines"][0]["allocated_qty"] == 40

    picklist = client.get(f"/orders/{order['id']}/picklist").json()
    assert sum(t["quantity"] for t in picklist) == 40
    assert picklist[0]["zone"] == "A"  # zone A picked first

    shipped = client.post(f"/orders/{order['id']}/ship").json()
    assert shipped["status"] == "shipped"

    remaining = client.get("/inventory", params={"sku": "SKU-1"}).json()
    assert sum(r["quantity"] for r in remaining) == 20


def test_partial_allocation_keeps_order_pending():
    make_product(sku="SKU-1")
    make_location(zone="A")
    client.post("/inventory/receive", json={"sku": "SKU-1", "location_code": "A-01-01-01", "quantity": 10})

    order = client.post(
        "/orders", json={"order_number": "ORD-2", "lines": [{"sku": "SKU-1", "quantity": 25}]}
    ).json()
    allocated = client.post(f"/orders/{order['id']}/allocate").json()
    assert allocated["status"] == "pending"
    assert allocated["lines"][0]["allocated_qty"] == 10

    # shipping a pending order is rejected
    assert client.post(f"/orders/{order['id']}/ship").status_code == 422


def test_ship_rejects_stale_allocation():
    make_product(sku="SKU-1")
    make_location(zone="A")
    make_location(zone="B")
    client.post("/inventory/receive", json={"sku": "SKU-1", "location_code": "A-01-01-01", "quantity": 20})

    order = client.post(
        "/orders", json={"order_number": "ORD-3", "lines": [{"sku": "SKU-1", "quantity": 20}]}
    ).json()
    client.post(f"/orders/{order['id']}/allocate")

    # stock moves away after allocation
    client.post(
        "/inventory/transfer",
        json={"sku": "SKU-1", "from_location": "A-01-01-01", "to_location": "B-01-01-01", "quantity": 15},
    )
    resp = client.post(f"/orders/{order['id']}/ship")
    assert resp.status_code == 409
