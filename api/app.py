import csv
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Inventory API")

PRODUCTS_CSV = Path(__file__).parent.parent / "products.csv"
csv_lock = threading.Lock()


class ProductInput(BaseModel):
    name: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=0)
    unit: str = Field(..., min_length=1)


class Product(ProductInput):
    id: int


class StockDelta(BaseModel):
    delta: int


def init_csv():
    """Initialize products.csv with sample data if it doesn't exist."""
    if PRODUCTS_CSV.exists():
        return
    
    sample_products = [
        {"id": 1, "name": "Leche de Avena", "quantity": 25, "unit": "litros"},
        {"id": 2, "name": "Café Arábica", "quantity": 8, "unit": "kg"},
        {"id": 3, "name": "Vasos Desechables", "quantity": 150, "unit": "unidades"},
        {"id": 4, "name": "Azúcar Moreno", "quantity": 5, "unit": "kg"},
        {"id": 5, "name": "Chocolate en Polvo", "quantity": 12, "unit": "kg"},
        {"id": 6, "name": "Té de Manzanilla", "quantity": 3, "unit": "paquetes"},
        {"id": 7, "name": "Almendras Tostadas", "quantity": 9, "unit": "kg"},
        {"id": 8, "name": "Canela Molida", "quantity": 2, "unit": "kg"},
    ]
    
    with csv_lock:
        with open(PRODUCTS_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name", "quantity", "unit"])
            writer.writeheader()
            writer.writerows(sample_products)


def read_products() -> list[dict]:
    """Read all products from CSV."""
    if not PRODUCTS_CSV.exists():
        return []
    
    with csv_lock:
        with open(PRODUCTS_CSV, "r") as f:
            reader = csv.DictReader(f)
            products = list(reader) if reader else []
    
    return [
        {
            "id": int(p["id"]),
            "name": p["name"],
            "quantity": int(p["quantity"]),
            "unit": p["unit"],
        }
        for p in products
    ]


def write_products(products: list[dict]):
    """Write products to CSV with lock."""
    with csv_lock:
        with open(PRODUCTS_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name", "quantity", "unit"])
            writer.writeheader()
            for p in products:
                writer.writerow(p)


def get_next_id() -> int:
    """Get the next available product ID."""
    products = read_products()
    return max((p["id"] for p in products), default=0) + 1


@app.on_event("startup")
async def startup():
    init_csv()


@app.get("/inventory")
async def list_inventory() -> list[Product]:
    """List all products in inventory."""
    products = read_products()
    return [Product(**p) for p in products]


@app.post("/inventory", status_code=201)
async def add_product(product: ProductInput) -> Product:
    """Add a new product to inventory."""
    products = read_products()
    
    name_lower = product.name.lower()
    if any(p["name"].lower() == name_lower for p in products):
        raise HTTPException(
            status_code=409,
            detail=f"El producto '{product.name}' ya existe en el inventario.",
        )
    
    new_id = get_next_id()
    new_product = {
        "id": new_id,
        "name": product.name,
        "quantity": product.quantity,
        "unit": product.unit,
    }
    products.append(new_product)
    write_products(products)
    
    return Product(**new_product)


@app.get("/inventory/alerts")
async def get_alerts(threshold: int = 10) -> list[Product]:
    """Get products with quantity below threshold."""
    products = read_products()
    low_stock = [p for p in products if p["quantity"] < threshold]
    return [Product(**p) for p in low_stock]


@app.patch("/inventory/{product_id}")
async def update_stock(product_id: int, delta: StockDelta) -> Product:
    """Update product quantity by delta."""
    products = read_products()
    
    product = next((p for p in products if p["id"] == product_id), None)
    if product is None:
        raise HTTPException(
            status_code=404,
            detail=f"Producto con ID {product_id} no encontrado.",
        )
    
    new_quantity = product["quantity"] + delta.delta
    if new_quantity < 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede establecer cantidad negativa. Stock actual: {product['quantity']}, delta: {delta.delta}",
        )
    
    product["quantity"] = new_quantity
    write_products(products)
    
    return Product(**product)
