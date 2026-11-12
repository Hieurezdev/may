"""Catalog HTTP endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..db import connection
from ..discovery import normalize
from ..dtos.catalog import Product
from ..fulfillment import catalog_product as product_from_row

router = APIRouter()


@router.get("/api/categories")
def categories() -> list[dict[str, str]]:
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM categories")]


@router.get("/api/products", response_model=list[Product])
def products(q: str = Query(default="", max_length=200), category: str = "", sort: Literal["featured", "new", "price-asc", "price-desc", "rating"] = "featured", try_on: bool = False) -> list[Product]:
    with connection() as db:
        query = "SELECT p.*,c.name AS category_name FROM products p JOIN categories c ON c.id=p.category WHERE p.active=1"
        if sort == "new":
            query += " ORDER BY p.collected_at DESC,p.rowid DESC"
        rows = db.execute(query).fetchall()
        words = normalize(q).split()
        selected = [row for row in rows if (not category or row["category"] == category)
                    and (not try_on or row["try_on"])
                    and all(word in normalize(f'{row["name"]} {row["brand"]} {row["category_name"]}') for word in words)]
        key = "price" if sort.startswith("price") else "rating" if sort == "rating" else "sold"
        if sort not in {"featured", "new"}:
            selected.sort(key=lambda row: row[key] or 0, reverse=sort != "price-asc")
        return [product_from_row(db, row) for row in selected]


@router.get("/api/products/{product_id}", response_model=Product)
def product_detail(product_id: str) -> Product:
    with connection() as db:
        row = db.execute("SELECT * FROM products WHERE id=? AND active=1", (product_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Sản phẩm không còn khả dụng.")
        return product_from_row(db, row)
