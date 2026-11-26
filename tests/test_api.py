import csv
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app, init_csv, PRODUCTS_CSV, csv_lock


@pytest.fixture
def temp_csv():
    """Fixture to use a temporary CSV for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as f:
        temp_path = Path(f.name)
        writer = csv.DictWriter(f, fieldnames=['id', 'name', 'quantity', 'unit'])
        writer.writeheader()
        writer.writerows([
            {'id': 1, 'name': 'Leche de Avena', 'quantity': 25, 'unit': 'litros'},
            {'id': 2, 'name': 'Café Arábica', 'quantity': 8, 'unit': 'kg'},
            {'id': 3, 'name': 'Vasos Desechables', 'quantity': 150, 'unit': 'unidades'},
        ])
    
    # Monkey-patch PRODUCTS_CSV
    import api.app as app_module
    original_csv = app_module.PRODUCTS_CSV
    app_module.PRODUCTS_CSV = temp_path
    
    yield temp_path
    
    # Restore and cleanup
    app_module.PRODUCTS_CSV = original_csv
    temp_path.unlink(missing_ok=True)


@pytest.fixture
def client(temp_csv):
    """Fixture to provide a TestClient with temporary CSV."""
    return TestClient(app)


def test_list_inventory(client):
    """Test listing all products."""
    response = client.get("/inventory")
    assert response.status_code == 200
    products = response.json()
    assert len(products) == 3
    assert products[0]['name'] == 'Leche de Avena'


def test_add_product_success(client):
    """Test adding a new product."""
    response = client.post("/inventory", json={
        "name": "Espresso",
        "quantity": 20,
        "unit": "kg"
    })
    assert response.status_code == 201
    product = response.json()
    assert product['name'] == 'Espresso'
    assert product['quantity'] == 20
    assert product['id'] == 4


def test_add_product_duplicate_409(client):
    """Test that adding duplicate product returns 409."""
    response = client.post("/inventory", json={
        "name": "Leche de Avena",
        "quantity": 10,
        "unit": "litros"
    })
    assert response.status_code == 409
    assert "ya existe" in response.json()['detail']


def test_add_product_duplicate_case_insensitive(client):
    """Test that duplicate check is case-insensitive."""
    response = client.post("/inventory", json={
        "name": "LECHE DE AVENA",
        "quantity": 5,
        "unit": "litros"
    })
    assert response.status_code == 409


def test_patch_stock_positive(client):
    """Test increasing stock."""
    response = client.patch("/inventory/1", json={"delta": 10})
    assert response.status_code == 200
    product = response.json()
    assert product['quantity'] == 35
    assert product['id'] == 1


def test_patch_stock_negative(client):
    """Test decreasing stock."""
    response = client.patch("/inventory/2", json={"delta": -5})
    assert response.status_code == 200
    product = response.json()
    assert product['quantity'] == 3


def test_patch_stock_would_go_negative_400(client):
    """Test that going negative returns 400."""
    response = client.patch("/inventory/2", json={"delta": -10})
    assert response.status_code == 400
    assert "negativa" in response.json()['detail']


def test_patch_nonexistent_product_404(client):
    """Test that updating nonexistent product returns 404."""
    response = client.patch("/inventory/999", json={"delta": 1})
    assert response.status_code == 404
    assert "no encontrado" in response.json()['detail']


def test_get_alerts_default_threshold(client):
    """Test alerts with default threshold (10)."""
    response = client.get("/inventory/alerts")
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 1
    assert alerts[0]['id'] == 2
    assert alerts[0]['quantity'] == 8


def test_get_alerts_custom_threshold(client):
    """Test alerts with custom threshold."""
    response = client.get("/inventory/alerts?threshold=50")
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 2  # Leche (25) and Café (8)
    ids = [a['id'] for a in alerts]
    assert 1 in ids
    assert 2 in ids


def test_persistence(client, temp_csv):
    """Test that changes persist in CSV."""
    # Add product
    response = client.post("/inventory", json={
        "name": "Pan de Avena",
        "quantity": 50,
        "unit": "unidades"
    })
    assert response.status_code == 201
    
    # Update stock
    response = client.patch("/inventory/1", json={"delta": 5})
    assert response.status_code == 200
    
    # Verify persistence by reading CSV directly
    with open(temp_csv, 'r') as f:
        reader = csv.DictReader(f)
        products = list(reader)
    
    # Check new product exists
    new_product = next((p for p in products if p['name'] == 'Pan de Avena'), None)
    assert new_product is not None
    assert new_product['quantity'] == '50'
    
    # Check updated quantity
    leche = next(p for p in products if p['name'] == 'Leche de Avena')
    assert leche['quantity'] == '30'  # 25 + 5


def test_add_product_empty_name(client):
    """Test that empty name is rejected."""
    response = client.post("/inventory", json={
        "name": "",
        "quantity": 10,
        "unit": "kg"
    })
    assert response.status_code == 422  # Validation error


def test_add_product_negative_quantity(client):
    """Test that negative quantity is rejected."""
    response = client.post("/inventory", json={
        "name": "Producto",
        "quantity": -5,
        "unit": "kg"
    })
    assert response.status_code == 422  # Validation error
