from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from typing import Optional, List
import json
from pathlib import Path
from datetime import datetime, timezone
import csv
import io
import fcntl
import threading
from collections import defaultdict
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from auth import authenticate, verify_token

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Item(BaseModel):
    name: str
    price: float
    description: Optional[str] = None
    category: Optional[str] = "General"
    in_stock: bool = True
    quantity: int = 0
    tags: List[str] = []

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError("Name must not be empty")
        return v.strip()

    @field_validator("price")
    @classmethod
    def price_must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError("Price must be non-negative")
        return v

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError("Quantity must be non-negative")
        return v

class LoginRequest(BaseModel):
    username: str
    password: str

class BulkUpdateRequest(BaseModel):
    item_ids: List[int]
    updates: dict

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, v):
        allowed_fields = {"name", "price", "description", "category", "in_stock", "quantity", "tags"}
        invalid_keys = set(v.keys()) - allowed_fields
        if invalid_keys:
            raise ValueError(f"Invalid update fields: {invalid_keys}")
        # Type-check values
        type_checks = {
            "name": str,
            "price": (int, float),
            "description": (str, type(None)),
            "category": (str, type(None)),
            "in_stock": bool,
            "quantity": int,
            "tags": list,
        }
        for key, value in v.items():
            expected = type_checks[key]
            # bool is subclass of int in Python, so explicitly reject bools for numeric fields
            if key in ("quantity", "price") and isinstance(value, bool):
                raise ValueError(f"Field '{key}' must be a number, not a boolean")
            if not isinstance(value, expected):
                raise ValueError(f"Field '{key}' has invalid type: expected {expected}, got {type(value).__name__}")
        if "price" in v and v["price"] < 0:
            raise ValueError("Price must be non-negative")
        if "quantity" in v and v["quantity"] < 0:
            raise ValueError("Quantity must be non-negative")
        if "name" in v and not v["name"].strip():
            raise ValueError("Name must not be empty")
        return v

items_db = []
next_id = 1
active_connections = []
activity_log = []
db_lock = threading.Lock()

MAX_ACTIVITY_LOG = 1000

DB_FILE = "items.json"

def load_db():
    global items_db, next_id
    if Path(DB_FILE).exists():
        try:
            with open(DB_FILE) as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                    items_db = data.get("items", [])
                    next_id = data.get("next_id", 1)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except (json.JSONDecodeError, ValueError, KeyError):
            # Corrupted file - start with empty database
            items_db = []
            next_id = 1

def save_db():
    with db_lock:
        with open(DB_FILE, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump({"items": items_db, "next_id": next_id}, f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

load_db()

def log_activity(action: str, item: str):
    activity_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "item": item
    })
    # Cap the log to prevent unbounded memory growth
    if len(activity_log) > MAX_ACTIVITY_LOG:
        del activity_log[:len(activity_log) - MAX_ACTIVITY_LOG]

async def broadcast(message: dict):
    disconnected = []
    for ws in active_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        active_connections.remove(ws)

@app.post("/api/login")
def login(req: LoginRequest):
    token = authenticate(req.username, req.password)
    if token:
        return {"token": token, "username": req.username}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

@app.get("/api/items")
def get_items(search: Optional[str] = None, category: Optional[str] = None, sort: Optional[str] = None):
    result = items_db
    if search:
        result = [i for i in result if search.lower() in i["name"].lower() or search.lower() in (i.get("description") or "").lower()]
    if category:
        result = [i for i in result if i.get("category") == category]
    if sort == "price_asc":
        result = sorted(result, key=lambda x: x["price"])
    elif sort == "price_desc":
        result = sorted(result, key=lambda x: x["price"], reverse=True)
    elif sort == "name":
        result = sorted(result, key=lambda x: x["name"])
    return result

@app.get("/api/categories")
def get_categories():
    return list(set(i.get("category", "General") for i in items_db))

@app.get("/api/stats")
def get_stats():
    low_stock = [i for i in items_db if i.get("quantity", 0) < 5]
    by_category = defaultdict(int)
    for item in items_db:
        by_category[item.get("category", "General")] += 1
    return {
        "total": len(items_db),
        "in_stock": sum(1 for i in items_db if i.get("in_stock", True)),
        "total_value": round(sum(i["price"] * i.get("quantity", 0) for i in items_db), 2),
        "low_stock": len(low_stock),
        "categories": len(set(i.get("category", "General") for i in items_db)),
        "by_category": dict(by_category),
        "avg_price": round(sum(i["price"] for i in items_db) / len(items_db), 2) if items_db else 0
    }

@app.get("/api/analytics")
def get_analytics():
    price_ranges = {"0-10": 0, "10-50": 0, "50-100": 0, "100+": 0}
    for item in items_db:
        p = item["price"]
        if p < 10: price_ranges["0-10"] += 1
        elif p < 50: price_ranges["10-50"] += 1
        elif p < 100: price_ranges["50-100"] += 1
        else: price_ranges["100+"] += 1
    
    return {
        "price_distribution": price_ranges,
        "stock_status": {
            "in_stock": sum(1 for i in items_db if i.get("in_stock", True)),
            "out_of_stock": sum(1 for i in items_db if not i.get("in_stock", True))
        },
        "recent_activity": activity_log[-10:][::-1]
    }

@app.get("/api/activity")
def get_activity(limit: int = 50):
    capped_limit = min(max(limit, 1), 500)
    return activity_log[-capped_limit:][::-1]

@app.get("/api/low-stock")
def get_low_stock():
    return [i for i in items_db if i.get("quantity", 0) < 5]

@app.get("/api/export/csv")
def export_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "name", "price", "quantity", "category", "description", "in_stock", "tags"])
    writer.writeheader()
    for item in items_db:
        writer.writerow({
            "id": item["id"],
            "name": item["name"],
            "price": item["price"],
            "quantity": item.get("quantity", 0),
            "category": item.get("category", "General"),
            "description": item.get("description", ""),
            "in_stock": item.get("in_stock", True),
            "tags": ",".join(item.get("tags", []))
        })
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=items.csv"}
    )

@app.get("/api/export/pdf")
def export_pdf():
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 750, "Inventory Report")
    p.setFont("Helvetica", 10)
    
    y = 720
    for item in items_db[:30]:  # Limit to 30 items
        text = f"{item['name']} - ${item['price']} - Qty: {item.get('quantity', 0)}"
        p.drawString(50, y, text)
        y -= 20
        if y < 50:
            break
    
    p.showPage()
    p.save()
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=inventory.pdf"}
    )

@app.post("/api/backup/schedule")
async def schedule_backup(background_tasks: BackgroundTasks, user: str = Depends(verify_token)):
    # Deep snapshot current state to avoid race conditions with the background task
    snapshot = json.loads(json.dumps({"items": items_db, "next_id": next_id}))
    
    def create_backup():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_{timestamp}.json"
        with open(backup_file, "w") as f:
            json.dump(snapshot, f)
    
    background_tasks.add_task(create_backup)
    return {"status": "backup scheduled"}

@app.post("/api/bulk-update")
async def bulk_update(req: BulkUpdateRequest, user: str = Depends(verify_token)):
    count = 0
    updated_names = []
    for item in items_db:
        if item["id"] in req.item_ids:
            item.update(req.updates)
            updated_names.append(item["name"])
            count += 1
    save_db()
    log_activity("bulk_updated", f"{count} items: {', '.join(updated_names[:5])}")
    await broadcast({"message": f"{count} items bulk updated by {user}"})
    return {"updated": count}

@app.post("/api/duplicate/{item_id}")
async def duplicate_item(item_id: int, user: str = Depends(verify_token)):
    global next_id
    item = next((i for i in items_db if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    new_item = {**item, "id": next_id, "name": f"{item['name']} (Copy)"}
    items_db.append(new_item)
    next_id += 1
    save_db()
    log_activity("duplicated", new_item["name"])
    await broadcast({"message": f"Item '{new_item['name']}' duplicated by {user}"})
    return new_item

@app.get("/api/search/advanced")
def advanced_search(
    q: Optional[str] = None,
    min_qty: Optional[int] = None,
    max_qty: Optional[int] = None,
    tags: Optional[str] = None
):
    result = items_db
    if q:
        result = [i for i in result if q.lower() in i["name"].lower() or q.lower() in (i.get("description") or "").lower()]
    if min_qty is not None:
        result = [i for i in result if i.get("quantity", 0) >= min_qty]
    if max_qty is not None:
        result = [i for i in result if i.get("quantity", 0) <= max_qty]
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        result = [i for i in result if any(t in i.get("tags", []) for t in tag_list)]
    return result

@app.get("/api/items/{item_id}")
def get_item(item_id: int):
    item = next((i for i in items_db if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.post("/api/items")
async def create_item(item: Item, user: str = Depends(verify_token)):
    global next_id
    new_item = {"id": next_id, **item.model_dump()}
    items_db.append(new_item)
    log_activity("created", item.name)
    next_id += 1
    save_db()
    await broadcast({"message": f"Item '{item.name}' created by {user}"})
    return new_item

@app.put("/api/items/{item_id}")
async def update_item(item_id: int, item: Item, user: str = Depends(verify_token)):
    for i, db_item in enumerate(items_db):
        if db_item["id"] == item_id:
            items_db[i] = {"id": item_id, **item.model_dump()}
            save_db()
            log_activity("updated", item.name)
            await broadcast({"message": f"Item '{item.name}' updated by {user}"})
            return items_db[i]
    raise HTTPException(status_code=404, detail="Item not found")

@app.delete("/api/items/{item_id}")
async def delete_item(item_id: int, user: str = Depends(verify_token)):
    global items_db
    item = next((i for i in items_db if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    log_activity("deleted", item["name"])
    items_db = [i for i in items_db if i["id"] != item_id]
    save_db()
    await broadcast({"message": f"Item '{item['name']}' deleted by {user}"})
    return {"deleted": item_id}

@app.get("/api/export")
def export_items():
    return items_db

@app.post("/api/items/batch")
async def batch_create(items: List[Item], user: str = Depends(verify_token)):
    global next_id
    created = []
    for item in items:
        new_item = {"id": next_id, **item.model_dump()}
        items_db.append(new_item)
        created.append(new_item)
        log_activity("created", item.name)
        next_id += 1
    save_db()
    await broadcast({"message": f"{len(created)} items batch created by {user}"})
    return {"created": len(created), "items": created}

@app.get("/api/reports/summary")
def get_summary_report():
    total_items = len(items_db)
    total_value = sum(i["price"] * i.get("quantity", 0) for i in items_db)
    avg_price = sum(i["price"] for i in items_db) / total_items if total_items else 0
    
    top_categories = defaultdict(lambda: {"count": 0, "value": 0})
    for item in items_db:
        cat = item.get("category", "General")
        top_categories[cat]["count"] += 1
        top_categories[cat]["value"] += item["price"] * item.get("quantity", 0)
    
    return {
        "total_items": total_items,
        "total_value": round(total_value, 2),
        "average_price": round(avg_price, 2),
        "top_categories": dict(sorted(top_categories.items(), key=lambda x: x[1]["value"], reverse=True)[:5]),
        "low_stock_count": len([i for i in items_db if i.get("quantity", 0) < 5])
    }

@app.post("/api/import")
async def import_items(file: UploadFile = File(...), user: str = Depends(verify_token)):
    global items_db, next_id
    try:
        content = await file.read()
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception:
        raise HTTPException(status_code=400, detail="Error reading uploaded file")
    
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="Expected a JSON array of items")
    
    # Validate each item has required fields
    validated_items = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"Item at index {idx} is not a valid object")
        if "name" not in item or "price" not in item:
            raise HTTPException(status_code=400, detail=f"Item at index {idx} missing required fields (name, price)")
        if not str(item["name"]).strip():
            raise HTTPException(status_code=400, detail=f"Item at index {idx} has empty name")
        try:
            price = float(item["price"])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Item at index {idx} has invalid price")
        if isinstance(item["price"], bool):
            raise HTTPException(status_code=400, detail=f"Item at index {idx} has invalid price (boolean not allowed)")
        if price < 0:
            raise HTTPException(status_code=400, detail=f"Item at index {idx} has negative price")
        try:
            quantity = int(item.get("quantity", 0))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Item at index {idx} has invalid quantity")
        if isinstance(item.get("quantity", 0), bool):
            raise HTTPException(status_code=400, detail=f"Item at index {idx} has invalid quantity (boolean not allowed)")
        if quantity < 0:
            raise HTTPException(status_code=400, detail=f"Item at index {idx} has negative quantity")
        raw_tags = item.get("tags", [])
        if not isinstance(raw_tags, list):
            raise HTTPException(status_code=400, detail=f"Item at index {idx} has invalid tags (must be an array)")
        tags = [str(t) for t in raw_tags if isinstance(t, str)]
        validated_items.append({
            "id": item.get("id", idx + 1),
            "name": str(item["name"]).strip(),
            "price": price,
            "description": item.get("description"),
            "category": item.get("category", "General"),
            "in_stock": bool(item.get("in_stock", True)),
            "quantity": quantity,
            "tags": tags
        })
    
    # Reassign sequential IDs to avoid conflicts
    for idx, item in enumerate(validated_items):
        item["id"] = idx + 1
    
    items_db = validated_items
    next_id = len(items_db) + 1
    save_db()
    log_activity("imported", f"{len(items_db)} items")
    await broadcast({"message": f"{len(items_db)} items imported by {user}"})
    return {"imported": len(items_db)}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
