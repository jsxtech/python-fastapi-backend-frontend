from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, WebSocket, Query, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import json
from pathlib import Path
from datetime import datetime, timedelta
import csv
import io
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

class LoginRequest(BaseModel):
    username: str
    password: str

items_db = []
next_id = 1
active_connections = []
activity_log = []

DB_FILE = "items.json"

def load_db():
    global items_db, next_id
    if Path(DB_FILE).exists():
        with open(DB_FILE) as f:
            data = json.load(f)
            items_db = data.get("items", [])
            next_id = data.get("next_id", 1)

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump({"items": items_db, "next_id": next_id}, f)

load_db()

async def broadcast(message: dict):
    for ws in active_connections:
        try:
            await ws.send_json(message)
        except:
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
    except:
        active_connections.remove(websocket)

@app.get("/api/items")
def get_items(search: Optional[str] = None, category: Optional[str] = None, sort: Optional[str] = None):
    result = items_db
    if search:
        result = [i for i in result if search.lower() in i["name"].lower()]
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
    low_stock = [i for i in items_db if i.get("quantity", 0) < 5 and i.get("quantity", 0) > 0]
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
    return activity_log[-limit:][::-1]

@app.get("/api/low-stock")
def get_low_stock():
    return [i for i in items_db if i.get("quantity", 0) < 5 and i.get("quantity", 0) > 0]

@app.get("/api/export/csv")
def export_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "name", "price", "quantity", "category", "description", "in_stock"])
    writer.writeheader()
    for item in items_db:
        writer.writerow({
            "id": item["id"],
            "name": item["name"],
            "price": item["price"],
            "quantity": item.get("quantity", 0),
            "category": item.get("category", "General"),
            "description": item.get("description", ""),
            "in_stock": item.get("in_stock", True)
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
async def schedule_backup(background_tasks: BackgroundTasks):
    def create_backup():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_{timestamp}.json"
        with open(backup_file, "w") as f:
            json.dump({"items": items_db, "next_id": next_id}, f)
    
    background_tasks.add_task(create_backup)
    return {"status": "backup scheduled"}

@app.post("/api/bulk-update")
def bulk_update(item_ids: List[int], updates: dict):
    count = 0
    for item in items_db:
        if item["id"] in item_ids:
            item.update(updates)
            count += 1
    save_db()
    return {"updated": count}

@app.post("/api/duplicate/{item_id}")
def duplicate_item(item_id: int):
    global next_id
    item = next((i for i in items_db if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    new_item = {**item, "id": next_id, "name": f"{item['name']} (Copy)"}
    items_db.append(new_item)
    next_id += 1
    save_db()
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
        result = [i for i in result if q.lower() in i["name"].lower() or q.lower() in i.get("description", "").lower()]
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
def create_item(item: Item):
    global next_id
    new_item = {"id": next_id, **item.dict()}
    items_db.append(new_item)
    activity_log.append({
        "timestamp": datetime.now().isoformat(),
        "action": "created",
        "item": item.name
    })
    next_id += 1
    save_db()
    return new_item

@app.put("/api/items/{item_id}")
def update_item(item_id: int, item: Item):
    for i, db_item in enumerate(items_db):
        if db_item["id"] == item_id:
            items_db[i] = {"id": item_id, **item.dict()}
            save_db()
            return items_db[i]
    raise HTTPException(status_code=404, detail="Item not found")

@app.delete("/api/items/{item_id}")
def delete_item(item_id: int):
    global items_db
    item = next((i for i in items_db if i["id"] == item_id), None)
    if item:
        activity_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "deleted",
            "item": item["name"]
        })
    items_db = [i for i in items_db if i["id"] != item_id]
    save_db()
    return {"deleted": item_id}

@app.post("/api/export")
def export_items():
    return items_db

@app.post("/api/items/batch")
def batch_create(items: List[Item]):
    global next_id
    created = []
    for item in items:
        new_item = {"id": next_id, **item.dict()}
        items_db.append(new_item)
        created.append(new_item)
        next_id += 1
    save_db()
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
        "low_stock_count": len([i for i in items_db if i.get("quantity", 0) < 5 and i.get("quantity", 0) > 0])
    }

@app.post("/api/import")
async def import_items(file: UploadFile = File(...)):
    content = await file.read()
    data = json.loads(content)
    global items_db, next_id
    items_db = data
    next_id = max([i["id"] for i in items_db], default=0) + 1
    save_db()
    return {"imported": len(items_db)}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
