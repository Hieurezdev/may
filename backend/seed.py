"""Validated snapshot of publicly available product data. Stock belongs to this demo."""

from pathlib import Path
from typing import TypedDict

from pydantic import TypeAdapter


class SeedProduct(TypedDict):
    id: str
    name: str
    brand: str
    category: str
    price: int
    original_price: int
    image: str
    rating: float | None
    sold: int | None
    try_on: str | None
    tag: str
    specs: dict[str, str]
    source_url: str
    collected_at: str
    sizes: list[str]
    colors: list[str]
    image_source_url: str


CATEGORIES = [
    ("tops", "Áo", "shirt"), ("bottoms", "Quần", "trousers"),
    ("dresses", "Váy & đầm", "dress"), ("outerwear", "Áo khoác", "jacket"),
    ("glasses", "Kính mắt", "glasses"), ("watches", "Đồng hồ", "watch"),
]

PRODUCTS = TypeAdapter(list[SeedProduct]).validate_json(
    Path(__file__).with_name("catalog.json").read_text()
)
