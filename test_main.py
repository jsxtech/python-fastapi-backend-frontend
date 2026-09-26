"""Test suite for the FastAPI inventory manager.

Each test runs against a freshly imported `main` module whose DB_FILE points at
an isolated temp file, so tests never touch the real items.json and don't
interfere with one another.
"""
import importlib
import io
import json
import sys
import threading

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_ctx(tmp_path, monkeypatch):
    """Import a clean `main` module with an isolated DB file.

    Optionally seed the DB file first by writing to `db_path` before the app
    is imported (done via the `seed` helper returned to the test).
    """
    db_file = tmp_path / "items.json"

    seeded = {}

    def seed(data):
        seeded["data"] = data
        db_file.write_text(json.dumps(data))

    def build():
        # Ensure a fresh import each time so module-level load_db() re-runs
        sys.modules.pop("main", None)
        import main  # noqa: WPS433 (import inside function is intentional)
        monkeypatch.setattr(main, "DB_FILE", str(db_file))
        main.load_db()  # reload against the isolated file
        return main, TestClient(main.app)

    return build, seed, db_file


@pytest.fixture
def client_pair(app_ctx):
    build, _seed, db_file = app_ctx
    main, client = build()
    return main, client, db_file


def auth_headers(client):
    res = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['token']}"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_login_success(client_pair):
    _main, client, _ = client_pair
    res = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    assert "token" in res.json()


def test_login_failure(client_pair):
    _main, client, _ = client_pair
    res = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_write_requires_auth(client_pair):
    _main, client, _ = client_pair
    res = client.post("/api/items", json={"name": "X", "price": 1.0})
    assert res.status_code in (401, 403)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def test_create_and_get_item(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = client.post("/api/items", json={"name": "Widget", "price": 9.99, "quantity": 3}, headers=h)
    assert res.status_code == 200
    item = res.json()
    assert item["id"] == 1
    assert item["name"] == "Widget"

    got = client.get(f"/api/items/{item['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "Widget"


def test_create_persists_to_disk(client_pair):
    main, client, db_file = client_pair
    h = auth_headers(client)
    client.post("/api/items", json={"name": "Persisted", "price": 5.0}, headers=h)
    saved = json.loads(db_file.read_text())
    assert saved["items"][0]["name"] == "Persisted"
    assert saved["next_id"] == 2


def test_update_item(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    client.post("/api/items", json={"name": "A", "price": 1.0}, headers=h)
    res = client.put("/api/items/1", json={"name": "B", "price": 2.0}, headers=h)
    assert res.status_code == 200
    assert res.json()["name"] == "B"


def test_update_missing_returns_404(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = client.put("/api/items/999", json={"name": "B", "price": 2.0}, headers=h)
    assert res.status_code == 404


def test_delete_item(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    client.post("/api/items", json={"name": "A", "price": 1.0}, headers=h)
    res = client.delete("/api/items/1", headers=h)
    assert res.status_code == 200
    assert client.get("/api/items/1").status_code == 404


def test_duplicate_item(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    client.post("/api/items", json={"name": "Orig", "price": 1.0}, headers=h)
    res = client.post("/api/duplicate/1", headers=h)
    assert res.status_code == 200
    assert res.json()["name"] == "Orig (Copy)"
    assert res.json()["id"] == 2


def test_batch_create_unique_ids(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    payload = [{"name": f"I{n}", "price": float(n)} for n in range(5)]
    res = client.post("/api/items/batch", json=payload, headers=h)
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()["items"]]
    assert ids == [1, 2, 3, 4, 5]
    assert len(set(ids)) == 5  # no duplicate IDs


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_create_rejects_negative_price(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = client.post("/api/items", json={"name": "X", "price": -1.0}, headers=h)
    assert res.status_code == 422


def test_create_rejects_empty_name(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = client.post("/api/items", json={"name": "   ", "price": 1.0}, headers=h)
    assert res.status_code == 422


def test_bulk_update_strips_name(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    client.post("/api/items", json={"name": "A", "price": 1.0}, headers=h)
    res = client.post("/api/bulk-update", json={"item_ids": [1], "updates": {"name": "  Trimmed  "}}, headers=h)
    assert res.status_code == 200
    assert client.get("/api/items/1").json()["name"] == "Trimmed"


def test_bulk_update_rejects_invalid_field(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = client.post("/api/bulk-update", json={"item_ids": [1], "updates": {"bogus": 1}}, headers=h)
    assert res.status_code == 422


def test_bulk_update_rejects_bool_as_price(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = client.post("/api/bulk-update", json={"item_ids": [1], "updates": {"price": True}}, headers=h)
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _upload(client, headers, payload):
    content = json.dumps(payload).encode()
    files = {"file": ("data.json", io.BytesIO(content), "application/json")}
    return client.post("/api/import", files=files, headers=headers)


def test_import_valid(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = _upload(client, h, [{"name": "Imported", "price": 3.0, "tags": ["a", "b"]}])
    assert res.status_code == 200
    assert res.json()["imported"] == 1
    assert client.get("/api/items/1").json()["tags"] == ["a", "b"]


def test_import_rejects_non_string_tags(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = _upload(client, h, [{"name": "X", "price": 1.0, "tags": ["ok", 123]}])
    assert res.status_code == 400
    assert "tags" in res.json()["detail"]


def test_import_rejects_missing_fields(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = _upload(client, h, [{"name": "X"}])
    assert res.status_code == 400


def test_import_rejects_non_array(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    res = _upload(client, h, {"not": "a list"})
    assert res.status_code == 400


def test_import_reassigns_sequential_ids(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    _upload(client, h, [
        {"id": 100, "name": "A", "price": 1.0},
        {"id": 100, "name": "B", "price": 2.0},  # duplicate id in input
    ])
    items = client.get("/api/items").json()
    ids = sorted(i["id"] for i in items)
    assert ids == [1, 2]


# ---------------------------------------------------------------------------
# Load-time validation (malformed items.json)
# ---------------------------------------------------------------------------

def test_load_drops_malformed_items(app_ctx):
    build, seed, _ = app_ctx
    seed({
        "items": [
            {"id": 1, "name": "Good", "price": 5.0, "quantity": 2},
            {"id": 2, "name": "NoPrice"},               # dropped: missing price
            {"id": 3, "price": 1.0},                    # dropped: missing name
            {"id": 4, "name": "", "price": 1.0},        # dropped: empty name
            "not a dict",                               # dropped: not an object
        ],
        "next_id": 5,
    })
    _main, client = build()
    items = client.get("/api/items").json()
    names = [i["name"] for i in items]
    assert names == ["Good"]


def test_stats_robust_after_load(app_ctx):
    build, seed, _ = app_ctx
    seed({"items": [{"id": 1, "name": "Good", "price": 10.0, "quantity": 2}], "next_id": 2})
    _main, client = build()
    # None of these should 500 even though the file was hand-seeded
    assert client.get("/api/stats").status_code == 200
    assert client.get("/api/analytics").status_code == 200
    assert client.get("/api/reports/summary").status_code == 200
    assert client.get("/api/export/pdf").status_code == 200
    stats = client.get("/api/stats").json()
    assert stats["total_value"] == 20.0


def test_load_corrupted_file_starts_empty(app_ctx):
    build, _seed, db_file = app_ctx
    db_file.write_text("{ this is not valid json ")
    _main, client = build()
    assert client.get("/api/items").json() == []


def test_next_id_recovers_from_max(app_ctx):
    build, seed, _ = app_ctx
    # next_id smaller than existing max id -> should be corrected to max+1
    seed({"items": [{"id": 50, "name": "X", "price": 1.0}], "next_id": 2})
    main, client = build()
    h = auth_headers(client)
    res = client.post("/api/items", json={"name": "New", "price": 1.0}, headers=h)
    assert res.json()["id"] == 51


# ---------------------------------------------------------------------------
# Concurrency: parallel creates must not collide on next_id
# ---------------------------------------------------------------------------

def test_concurrent_creates_unique_ids(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    results = []
    errors = []

    def worker(n):
        try:
            r = client.post("/api/items", json={"name": f"C{n}", "price": 1.0}, headers=h)
            results.append(r.json()["id"])
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 20
    assert len(set(results)) == 20  # every id is unique -> no lost updates


# ---------------------------------------------------------------------------
# Read endpoints / filters
# ---------------------------------------------------------------------------

def test_search_and_sort(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    client.post("/api/items", json={"name": "Apple", "price": 3.0}, headers=h)
    client.post("/api/items", json={"name": "Banana", "price": 1.0}, headers=h)
    asc = client.get("/api/items?sort=price_asc").json()
    assert [i["name"] for i in asc] == ["Banana", "Apple"]
    found = client.get("/api/items?search=app").json()
    assert len(found) == 1 and found[0]["name"] == "Apple"


def test_low_stock(client_pair):
    _main, client, _ = client_pair
    h = auth_headers(client)
    client.post("/api/items", json={"name": "Low", "price": 1.0, "quantity": 2}, headers=h)
    client.post("/api/items", json={"name": "High", "price": 1.0, "quantity": 50}, headers=h)
    low = client.get("/api/low-stock").json()
    assert [i["name"] for i in low] == ["Low"]
