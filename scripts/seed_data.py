"""Seed the warehouse with demo locations, products, and starting stock.

Usage: python -m scripts.seed_data
"""
import random

from app.database import Base, SessionLocal, engine
from app.models import Inventory, Location, Product, VelocityClass

random.seed(42)

PRODUCTS = [
    ("SKU-1001", "USB-C Cable 1m", "electronics", 2.10, VelocityClass.A, 200, 500),
    ("SKU-1002", "Wireless Mouse", "electronics", 8.50, VelocityClass.A, 150, 300),
    ("SKU-1003", "Mechanical Keyboard", "electronics", 32.00, VelocityClass.B, 60, 120),
    ("SKU-1004", "27in Monitor", "electronics", 145.00, VelocityClass.B, 30, 60),
    ("SKU-1005", "HDMI Cable 2m", "electronics", 3.40, VelocityClass.A, 200, 400),
    ("SKU-2001", "Desk Lamp", "furniture", 18.00, VelocityClass.C, 20, 50),
    ("SKU-2002", "Office Chair", "furniture", 89.00, VelocityClass.C, 10, 25),
    ("SKU-3001", "A4 Paper Ream", "supplies", 4.20, VelocityClass.A, 300, 600),
    ("SKU-3002", "Stapler", "supplies", 6.75, VelocityClass.C, 40, 80),
    ("SKU-3003", "Whiteboard Markers 4pk", "supplies", 5.10, VelocityClass.B, 100, 200),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Product).count() > 0:
            print("Database already seeded, skipping.")
            return

        locations = []
        for zone in ("A", "B", "C"):
            for aisle in (1, 2):
                for rack in (1, 2):
                    for bin_ in (1, 2, 3):
                        loc = Location(
                            code=f"{zone}-{aisle:02d}-{rack:02d}-{bin_:02d}",
                            zone=zone,
                            aisle=aisle,
                            rack=rack,
                            bin=bin_,
                            capacity=random.choice((200, 300, 500)),
                        )
                        locations.append(loc)
        db.add_all(locations)

        products = [
            Product(
                sku=sku,
                name=name,
                category=category,
                unit_cost=cost,
                velocity_class=velocity,
                reorder_point=rop,
                reorder_qty=roq,
            )
            for sku, name, category, cost, velocity, rop, roq in PRODUCTS
        ]
        db.add_all(products)
        db.flush()

        # scatter starting stock, deliberately mis-slotting a few SKUs
        for product in products:
            for _ in range(random.randint(1, 3)):
                loc = random.choice(locations)
                db.add(
                    Inventory(
                        product_id=product.id,
                        location_id=loc.id,
                        quantity=random.randint(20, 120),
                    )
                )
        db.commit()
        print(f"Seeded {len(products)} products, {len(locations)} locations.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
