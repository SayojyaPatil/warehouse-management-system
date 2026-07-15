"""Print a reorder report: every product at or below its reorder point.

Intended to run on a schedule (cron / CI job) against the live database.
Usage: python -m scripts.low_stock_report
"""
from sqlalchemy import func

from app.database import SessionLocal
from app.models import Inventory, Product


def run() -> None:
    db = SessionLocal()
    try:
        totals = (
            db.query(Product, func.coalesce(func.sum(Inventory.quantity), 0).label("total"))
            .outerjoin(Inventory)
            .group_by(Product.id)
            .order_by(Product.sku)
            .all()
        )
        flagged = [
            (p, total)
            for p, total in totals
            if p.reorder_point > 0 and total <= p.reorder_point
        ]
        if not flagged:
            print("All products above reorder points. Nothing to do.")
            return

        print(f"{'SKU':<12} {'Name':<28} {'On hand':>8} {'Reorder pt':>11} {'Order qty':>10}")
        print("-" * 73)
        for product, total in flagged:
            print(
                f"{product.sku:<12} {product.name:<28} {total:>8} "
                f"{product.reorder_point:>11} {product.reorder_qty:>10}"
            )
        print(f"\n{len(flagged)} product(s) need reordering.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
