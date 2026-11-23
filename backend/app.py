import os
import json
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Body
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

if __package__:
    from . import database, queue_engine
    from .database import get_db, PRESETS, load_preset
else:
    import database
    from database import get_db, PRESETS, load_preset
    import queue_engine

app = FastAPI(title="QueueLess - Smart Queue & Appointment System")

# Ensure static directories exist
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "static"))
os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# WebSocket Manager for real-time broadcasts
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for d in disconnected:
            self.disconnect(d)

manager = ConnectionManager()

# Pydantic Request Models
class TakeTokenRequest(BaseModel):
    service_id: str
    customer_name: str
    customer_phone: Optional[str] = ""
    customer_email: Optional[str] = ""
    notes: Optional[str] = ""
    is_priority: Optional[int] = 0
    token_type: Optional[str] = "REMOTE"

class CallNextRequest(BaseModel):
    counter_id: str
    operator_name: Optional[str] = None

class RecallRequest(BaseModel):
    counter_id: str

class CompleteTokenRequest(BaseModel):
    counter_id: str
    feedback_rating: Optional[int] = 5
    notes: Optional[str] = ""

class SkipTokenRequest(BaseModel):
    counter_id: str
    reason: Optional[str] = "No Show"

class TransferTokenRequest(BaseModel):
    token_id: int
    target_service_id: str
    reason: Optional[str] = "Transferred"

class CounterStatusRequest(BaseModel):
    counter_id: str
    is_active: int
    operator_name: Optional[str] = None

class BookAppointmentRequest(BaseModel):
    service_id: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = ""
    appointment_date: str
    slot_time: str
    notes: Optional[str] = ""

class CheckinAppointmentRequest(BaseModel):
    appointment_code: str

class SwitchPresetRequest(BaseModel):
    preset: str
    seed_data: Optional[bool] = True

class UpdateServiceRequest(BaseModel):
    service_id: str
    name: str
    default_service_time: int
    description: Optional[str] = ""
    is_active: Optional[int] = 1

class UpdateAnnouncementRequest(BaseModel):
    organization_name: str
    announcement_banner: str

@app.on_event("startup")
def startup_event():
    database.init_db()

# --- WebSocket Endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial ping/connection confirmation
        await websocket.send_json({"type": "CONNECTED", "message": "Connected to QueueLess live hub"})
        while True:
            data = await websocket.receive_text()
            # Can handle incoming client pings
            try:
                msg = json.loads(data)
                if msg.get("type") == "PING":
                    await websocket.send_json({"type": "PONG"})
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# --- Helper functions for notifications ---
async def notify_queue_change(event_type: str, data: dict = None):
    await manager.broadcast({
        "type": event_type,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "data": data or {}
    })

# --- HTML Views ---
@app.get("/", response_class=HTMLResponse)
async def get_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/display", response_class=HTMLResponse)
async def get_display():
    return FileResponse(os.path.join(STATIC_DIR, "display.html"))

@app.get("/operator", response_class=HTMLResponse)
async def get_operator():
    return FileResponse(os.path.join(STATIC_DIR, "operator.html"))

@app.get("/admin", response_class=HTMLResponse)
async def get_admin():
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))

@app.get("/ticket", response_class=HTMLResponse)
async def get_ticket():
    return FileResponse(os.path.join(STATIC_DIR, "ticket.html"))

# --- REST APIs ---

@app.get("/api/info")
def get_system_info():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings = {r["key"]: r["value"] for r in cursor.fetchall()}
    conn.close()
    return {
        "organization_name": settings.get("organization_name", "QueueLess Smart System"),
        "announcement_banner": settings.get("announcement_banner", "Welcome to QueueLess."),
        "active_preset": settings.get("active_preset", "university"),
        "presets_available": list(PRESETS.keys())
    }

@app.get("/api/services")
def list_services():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM services WHERE is_active = 1 ORDER BY name ASC")
    services = [dict(r) for r in cursor.fetchall()]

    # Augment with live queue estimates
    for srv in services:
        est = queue_engine.get_service_queue_estimate(cursor, srv["id"])
        cursor.execute("SELECT COUNT(*) as count FROM tokens WHERE service_id = ? AND status = 'WAITING'", (srv["id"],))
        waiting_count = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM tokens WHERE service_id = ? AND status = 'SERVING'", (srv["id"],))
        serving_count = cursor.fetchone()["count"]

        srv["waiting_count"] = waiting_count
        srv["serving_count"] = serving_count
        srv["active_counters"] = est["active_counters"]
        srv["dynamic_service_time"] = est["dynamic_service_time"]
        srv["estimated_wait_mins"] = est["estimated_wait_mins"]
        srv["expected_turn_time"] = est["expected_turn_time"]
        srv["status_message"] = est["message"]
        srv["formula_breakdown"] = est["formula_breakdown"]

    conn.close()
    return services

@app.get("/api/counters")
def list_counters():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, s.name as service_name, s.code as service_code, s.color as service_color,
               t.token_number as current_token_number, t.customer_name as current_customer_name,
               t.status as current_token_status, t.started_at as current_token_started_at,
               t.called_at as current_token_called_at, t.is_priority as current_is_priority
        FROM counters c
        LEFT JOIN services s ON c.service_id = s.id
        LEFT JOIN tokens t ON c.current_token_id = t.id
        ORDER BY c.name ASC
    """)
    counters = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return counters

@app.post("/api/tokens/take")
async def take_token(req: TakeTokenRequest):
    conn = get_db()
    try:
        token = queue_engine.generate_next_token(
            conn,
            service_id=req.service_id,
            customer_name=req.customer_name,
            customer_phone=req.customer_phone,
            customer_email=req.customer_email,
            notes=req.notes,
            is_priority=req.is_priority,
            token_type=req.token_type
        )
        cursor = conn.cursor()
        est = queue_engine.get_service_queue_estimate(cursor, req.service_id, token["id"])
        token.update(est)
    except ValueError as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))
    conn.close()

    await notify_queue_change("TOKEN_NEW", token)
    return token

@app.get("/api/tokens/{identifier}")
def get_token_details(identifier: str):
    conn = get_db()
    cursor = conn.cursor()

    if identifier.isdigit():
        cursor.execute("""
            SELECT t.*, s.name as service_name, s.code as service_code, s.color as service_color,
                   c.name as counter_name
            FROM tokens t
            JOIN services s ON t.service_id = s.id
            LEFT JOIN counters c ON t.counter_id = c.id
            WHERE t.id = ?
        """, (int(identifier),))
    else:
        cursor.execute("""
            SELECT t.*, s.name as service_name, s.code as service_code, s.color as service_color,
                   c.name as counter_name
            FROM tokens t
            JOIN services s ON t.service_id = s.id
            LEFT JOIN counters c ON t.counter_id = c.id
            WHERE UPPER(t.token_number) = UPPER(?)
        """, (identifier.strip(),))

    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Token not found")

    token_data = dict(row)
    est = queue_engine.get_service_queue_estimate(cursor, token_data["service_id"], token_data["id"])
    conn.close()

    token_data["estimate"] = est
    return token_data

@app.get("/api/queue/active")
def get_active_queue(service_id: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT t.*, s.name as service_name, s.code as service_code, s.color as service_color,
               c.name as counter_name
        FROM tokens t
        JOIN services s ON t.service_id = s.id
        LEFT JOIN counters c ON t.counter_id = c.id
        WHERE t.status IN ('WAITING', 'CALLED', 'SERVING')
    """
    params = []
    if service_id:
        query += " AND t.service_id = ?"
        params.append(service_id)

    query += " ORDER BY t.is_priority DESC, t.created_at ASC"
    cursor.execute(query, params)
    tokens = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return tokens

# --- Operator Actions ---
@app.post("/api/operator/call-next")
async def operator_call_next(req: CallNextRequest):
    conn = get_db()
    try:
        result = queue_engine.call_next_token(conn, req.counter_id, req.operator_name)
    except ValueError as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))
    conn.close()

    if not result:
        return {"status": "EMPTY", "message": "No waiting customers in queue for this service."}

    await notify_queue_change("TOKEN_CALLED", result)
    return result

@app.post("/api/operator/recall")
async def operator_recall(req: RecallRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, t.token_number, t.customer_name, s.name as service_name
        FROM counters c
        JOIN tokens t ON c.current_token_id = t.id
        JOIN services s ON c.service_id = s.id
        WHERE c.id = ?
    """, (req.counter_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=400, detail="No active token at this counter to recall")

    payload = {
        "counter_id": row["id"],
        "counter_name": row["name"],
        "token_number": row["token_number"],
        "customer_name": row["customer_name"],
        "service_name": row["service_name"]
    }
    await notify_queue_change("TOKEN_RECALLED", payload)
    return payload

@app.post("/api/operator/start-serving")
async def operator_start_serving(req: RecallRequest):
    conn = get_db()
    try:
        res = queue_engine.start_serving_token(conn, req.counter_id)
    except ValueError as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))
    conn.close()
    await notify_queue_change("TOKEN_SERVING", res)
    return res

@app.post("/api/operator/complete")
async def operator_complete(req: CompleteTokenRequest):
    conn = get_db()
    res = queue_engine.complete_token(conn, req.counter_id, req.feedback_rating, req.notes)
    conn.close()
    if res:
        await notify_queue_change("TOKEN_COMPLETED", res)
    return {"status": "OK", "result": res}

@app.post("/api/operator/skip")
async def operator_skip(req: SkipTokenRequest):
    conn = get_db()
    res = queue_engine.skip_token(conn, req.counter_id, req.reason)
    conn.close()
    if res:
        await notify_queue_change("TOKEN_SKIPPED", res)
    return {"status": "OK", "result": res}

@app.post("/api/operator/transfer")
async def operator_transfer(req: TransferTokenRequest):
    conn = get_db()
    try:
        res = queue_engine.transfer_token(conn, req.token_id, req.target_service_id, req.reason)
    except ValueError as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))
    conn.close()
    await notify_queue_change("TOKEN_TRANSFERRED", res)
    return res

@app.post("/api/operator/counter-status")
async def set_counter_status(req: CounterStatusRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE counters
        SET is_active = ?, current_operator = coalesce(?, current_operator), updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (req.is_active, req.operator_name, req.counter_id))
    conn.commit()
    conn.close()
    await notify_queue_change("COUNTER_UPDATED", {"counter_id": req.counter_id, "is_active": req.is_active})
    return {"status": "OK"}

# --- Public Big-Screen Display Feed ---
@app.get("/api/display-feed")
def get_display_feed():
    conn = get_db()
    cursor = conn.cursor()

    # Active counters with current tokens
    cursor.execute("""
        SELECT c.id as counter_id, c.name as counter_name, c.is_active, c.current_operator,
               t.token_number, t.customer_name, t.status as token_status, t.called_at,
               s.name as service_name, s.code as service_code, s.color as service_color
        FROM counters c
        LEFT JOIN tokens t ON c.current_token_id = t.id
        LEFT JOIN services s ON c.service_id = s.id
        WHERE c.is_active = 1
        ORDER BY c.name ASC
    """)
    counters = [dict(r) for r in cursor.fetchall()]

    # Up next in queue (next 10 WAITING)
    cursor.execute("""
        SELECT t.id, t.token_number, t.customer_name, t.is_priority, t.created_at,
               s.name as service_name, s.code as service_code, s.color as service_color
        FROM tokens t
        JOIN services s ON t.service_id = s.id
        WHERE t.status = 'WAITING'
        ORDER BY t.is_priority DESC, t.created_at ASC
        LIMIT 10
    """)
    up_next = [dict(r) for r in cursor.fetchall()]

    # Recently completed (last 6)
    cursor.execute("""
        SELECT t.token_number, t.completed_at, c.name as counter_name, s.name as service_name
        FROM tokens t
        JOIN services s ON t.service_id = s.id
        LEFT JOIN counters c ON t.counter_id = c.id
        WHERE t.status = 'COMPLETED'
        ORDER BY t.completed_at DESC
        LIMIT 6
    """)
    recently_served = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT value FROM settings WHERE key = 'announcement_banner'")
    announcement = cursor.fetchone()

    cursor.execute("SELECT value FROM settings WHERE key = 'organization_name'")
    org_name = cursor.fetchone()

    conn.close()
    return {
        "counters": counters,
        "up_next": up_next,
        "recently_served": recently_served,
        "announcement": announcement["value"] if announcement else "",
        "organization_name": org_name["value"] if org_name else "QueueLess System",
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }

# --- Appointments Engine ---
@app.get("/api/appointments/available-slots")
def get_available_slots(service_id: str, date_str: str):
    conn = get_db()
    cursor = conn.cursor()

    # Fixed slots from 09:00 to 16:30
    all_slots = [
        "09:00 - 09:30", "09:30 - 10:00",
        "10:00 - 10:30", "10:30 - 11:00",
        "11:00 - 11:30", "11:30 - 12:00",
        "13:00 - 13:30", "13:30 - 14:00",
        "14:00 - 14:30", "14:30 - 15:00",
        "15:00 - 15:30", "15:30 - 16:00",
        "16:00 - 16:30"
    ]

    cursor.execute("""
        SELECT slot_time, COUNT(*) as booked
        FROM appointments
        WHERE service_id = ? AND appointment_date = ? AND status != 'CANCELLED'
        GROUP BY slot_time
    """, (service_id, date_str))
    booked_counts = {r["slot_time"]: r["booked"] for r in cursor.fetchall()}
    conn.close()

    slot_capacity = 3
    result = []
    for s in all_slots:
        booked = booked_counts.get(s, 0)
        remaining = max(0, slot_capacity - booked)
        result.append({
            "slot_time": s,
            "capacity": slot_capacity,
            "booked": booked,
            "available": remaining > 0,
            "remaining": remaining
        })
    return result

@app.post("/api/appointments/book")
async def book_appointment(req: BookAppointmentRequest):
    conn = get_db()
    cursor = conn.cursor()

    # Generate appointment code
    cursor.execute("SELECT COUNT(*) as count FROM appointments")
    c = cursor.fetchone()["count"]
    apt_code = f"APT-{1001 + c}"

    cursor.execute("""
        INSERT INTO appointments (appointment_code, service_id, customer_name, customer_phone,
                                  customer_email, appointment_date, slot_time, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED')
    """, (apt_code, req.service_id, req.customer_name, req.customer_phone,
          req.customer_email, req.appointment_date, req.slot_time, req.notes))
    apt_id = cursor.lastrowid
    conn.commit()

    cursor.execute("SELECT a.*, s.name as service_name FROM appointments a JOIN services s ON a.service_id = s.id WHERE a.id = ?", (apt_id,))
    apt_data = dict(cursor.fetchone())
    conn.close()

    await notify_queue_change("APPOINTMENT_BOOKED", apt_data)
    return apt_data

@app.post("/api/appointments/checkin")
async def checkin_appointment(req: CheckinAppointmentRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM appointments WHERE UPPER(appointment_code) = UPPER(?)", (req.appointment_code.strip(),))
    apt = cursor.fetchone()
    if not apt:
        conn.close()
        raise HTTPException(status_code=404, detail="Appointment code not found")

    if apt["status"] == "CHECKED_IN" and apt["token_id"]:
        cursor.execute("SELECT * FROM tokens WHERE id = ?", (apt["token_id"],))
        tok = cursor.fetchone()
        conn.close()
        return {"status": "ALREADY_CHECKED_IN", "token": dict(tok)}

    # Generate Token for Checked-in appointment with priority=1
    tok_data = queue_engine.generate_next_token(
        conn,
        service_id=apt["service_id"],
        customer_name=apt["customer_name"],
        customer_phone=apt["customer_phone"],
        customer_email=apt["customer_email"],
        notes=f"Appt {apt['appointment_code']} ({apt['slot_time']})",
        is_priority=1, # Appointments get priority access
        token_type="APPOINTMENT"
    )

    cursor.execute("UPDATE appointments SET status = 'CHECKED_IN', token_id = ? WHERE id = ?", (tok_data["id"], apt["id"]))
    conn.commit()
    conn.close()

    await notify_queue_change("TOKEN_NEW", tok_data)
    return {"status": "CHECKED_IN", "token": tok_data}

@app.get("/api/appointments")
def list_appointments(date_str: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT a.*, s.name as service_name, s.code as service_code, t.token_number
        FROM appointments a
        JOIN services s ON a.service_id = s.id
        LEFT JOIN tokens t ON a.token_id = t.id
    """
    params = []
    if date_str:
        query += " WHERE a.appointment_date = ?"
        params.append(date_str)
    query += " ORDER BY a.appointment_date ASC, a.slot_time ASC"

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# --- Analytics & Reporting ---
@app.get("/api/analytics")
def get_analytics():
    conn = get_db()
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Overall totals today
    cursor.execute("SELECT COUNT(*) as count FROM tokens WHERE created_at >= ?", (today_str + " 00:00:00",))
    total_tokens_today = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM tokens WHERE status = 'COMPLETED' AND created_at >= ?", (today_str + " 00:00:00",))
    completed_today = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM tokens WHERE status = 'SKIPPED' AND created_at >= ?", (today_str + " 00:00:00",))
    skipped_today = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM tokens WHERE status = 'WAITING'")
    currently_waiting = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM tokens WHERE status = 'SERVING'")
    currently_serving = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT AVG(actual_wait_mins) as avg_wait, AVG(actual_service_mins) as avg_service
        FROM tokens
        WHERE status = 'COMPLETED' AND created_at >= ?
    """, (today_str + " 00:00:00",))
    averages = cursor.fetchone()
    avg_wait = round(averages["avg_wait"] or 0, 1)
    avg_service = round(averages["avg_service"] or 0, 1)

    # Hourly distribution
    hourly_counts = {f"{h:02d}:00": 0 for h in range(8, 18)}
    cursor.execute("""
        SELECT strftime('%H:00', created_at) as hour_slot, COUNT(*) as count
        FROM tokens
        WHERE created_at >= ?
        GROUP BY hour_slot
    """, (today_str + " 00:00:00",))
    for r in cursor.fetchall():
        if r["hour_slot"] in hourly_counts:
            hourly_counts[r["hour_slot"]] = r["count"]

    # Service breakdown
    cursor.execute("""
        SELECT s.name, s.color, COUNT(t.id) as token_count
        FROM services s
        LEFT JOIN tokens t ON s.id = t.service_id AND t.created_at >= ?
        GROUP BY s.id
    """, (today_str + " 00:00:00",))
    service_breakdown = [dict(r) for r in cursor.fetchall()]

    # Counter efficiency
    cursor.execute("""
        SELECT c.name as counter_name, c.current_operator,
               COUNT(t.id) as served_count,
               AVG(t.actual_service_mins) as avg_time
        FROM counters c
        LEFT JOIN tokens t ON c.id = t.counter_id AND t.status = 'COMPLETED' AND t.created_at >= ?
        GROUP BY c.id
    """, (today_str + " 00:00:00",))
    counter_efficiency = []
    for r in cursor.fetchall():
        counter_efficiency.append({
            "counter_name": r["counter_name"],
            "operator": r["current_operator"] or "Unassigned",
            "served_count": r["served_count"],
            "avg_time": round(r["avg_time"] or 0, 1)
        })

    conn.close()
    return {
        "summary": {
            "total_today": total_tokens_today,
            "completed_today": completed_today,
            "skipped_today": skipped_today,
            "currently_waiting": currently_waiting,
            "currently_serving": currently_serving,
            "avg_wait_mins": avg_wait,
            "avg_service_mins": avg_service
        },
        "hourly_distribution": hourly_counts,
        "service_breakdown": service_breakdown,
        "counter_efficiency": counter_efficiency
    }

# --- Admin & Preset APIs ---
@app.post("/api/admin/preset")
async def switch_preset(req: SwitchPresetRequest):
    if req.preset not in PRESETS:
        raise HTTPException(status_code=400, detail="Unknown preset key")
    load_preset(req.preset, seed_sample_tokens=req.seed_data)
    await notify_queue_change("PRESET_CHANGED", {"preset": req.preset})
    return {"status": "SUCCESS", "preset": req.preset}

@app.post("/api/admin/update-announcement")
async def update_announcement(req: UpdateAnnouncementRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'organization_name'", (req.organization_name,))
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'announcement_banner'", (req.announcement_banner,))
    conn.commit()
    conn.close()
    await notify_queue_change("ANNOUNCEMENT_UPDATED", {"organization_name": req.organization_name, "announcement_banner": req.announcement_banner})
    return {"status": "OK"}

@app.post("/api/admin/reset-queue")
async def reset_queue():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tokens")
    cursor.execute("UPDATE counters SET current_token_id = NULL")
    conn.commit()
    conn.close()
    await notify_queue_change("QUEUE_RESET", {})
    return {"status": "OK", "message": "All tokens cleared and counters reset."}

if __name__ == "__main__":
    import uvicorn
    print("Starting QueueLess server on http://127.0.0.1:8000 ...")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
