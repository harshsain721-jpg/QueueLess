import math
from datetime import datetime, timedelta
if __package__:
    from .database import get_db
else:
    from database import get_db

def calculate_dynamic_service_time(cursor, service_id, default_mins):
    """
    Computes dynamic service time using exponential moving average of recently completed
    tokens for this service today, combined with default nominal service time.
    """
    cursor.execute("""
        SELECT actual_service_mins 
        FROM tokens 
        WHERE service_id = ? AND status = 'COMPLETED' AND actual_service_mins > 0
        ORDER BY completed_at DESC 
        LIMIT 10
    """, (service_id,))
    rows = cursor.fetchall()

    if not rows:
        return float(default_mins)

    times = [r["actual_service_mins"] for r in rows]
    # Filter out crazy outliers (< 0.5 min or > 60 mins)
    valid_times = [t for t in times if 0.5 <= t <= 60]
    if not valid_times:
        return float(default_mins)

    avg_actual = sum(valid_times) / len(valid_times)
    # Blend: 70% actual recent performance + 30% nominal expectation
    dynamic = (0.7 * avg_actual) + (0.3 * default_mins)
    return round(dynamic, 1)

def get_service_queue_estimate(cursor, service_id, target_token_id=None):
    """
    Calculates waiting time estimation for a service or a specific token.
    Queue model: M/M/c approximation with priority queueing.
    """
    # 1. Get service info
    cursor.execute("SELECT * FROM services WHERE id = ?", (service_id,))
    service = cursor.fetchone()
    if not service:
        return {
            "people_ahead": 0,
            "estimated_wait_mins": 0,
            "active_counters": 0,
            "dynamic_service_time": 10,
            "expected_turn_time": "--:--",
            "message": "Service not found"
        }

    default_time = service["default_service_time"]
    dynamic_time = calculate_dynamic_service_time(cursor, service_id, default_time)

    # 2. Count active counters assigned to this service
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM counters 
        WHERE service_id = ? AND is_active = 1
    """, (service_id,))
    active_counters = cursor.fetchone()["count"]
    effective_counters = max(1, active_counters)

    # 3. Find people ahead in queue (ordered by is_priority DESC, created_at ASC)
    if target_token_id:
        cursor.execute("SELECT * FROM tokens WHERE id = ?", (target_token_id,))
        target_token = cursor.fetchone()
        if not target_token:
            return None
        
        # If token is already called or serving
        if target_token["status"] in ["CALLED", "SERVING"]:
            return {
                "token_number": target_token["token_number"],
                "status": target_token["status"],
                "people_ahead": 0,
                "estimated_wait_mins": 0,
                "active_counters": active_counters,
                "dynamic_service_time": dynamic_time,
                "expected_turn_time": "NOW",
                "counter_id": target_token["counter_id"],
                "operator_name": target_token["operator_name"],
                "message": f"Your turn now! Please report to Counter {target_token['counter_id'] or ''}"
            }
        elif target_token["status"] in ["COMPLETED", "SKIPPED", "CANCELLED"]:
            return {
                "token_number": target_token["token_number"],
                "status": target_token["status"],
                "people_ahead": 0,
                "estimated_wait_mins": 0,
                "active_counters": active_counters,
                "dynamic_service_time": dynamic_time,
                "expected_turn_time": "-",
                "message": f"Token has been {target_token['status'].lower()}."
            }

        # For WAITING token: Count tokens ahead
        target_prio = target_token["is_priority"]
        target_created = target_token["created_at"]
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM tokens
            WHERE service_id = ? AND status = 'WAITING'
            AND (
                (is_priority > ?) 
                OR (is_priority = ? AND created_at < ?)
                OR (is_priority = ? AND created_at = ? AND id < ?)
            )
        """, (service_id, target_prio, target_prio, target_created, target_prio, target_created, target_token_id))
        people_ahead = cursor.fetchone()["count"]
    else:
        # Generic query for incoming new token
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM tokens 
            WHERE service_id = ? AND status = 'WAITING'
        """, (service_id,))
        people_ahead = cursor.fetchone()["count"]

    # 4. Check if any counter is currently idle vs busy
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM counters 
        WHERE service_id = ? AND is_active = 1 AND current_token_id IS NOT NULL
    """, (service_id,))
    busy_counters = cursor.fetchone()["count"]

    # 5. Compute estimated wait minutes
    # If people_ahead == 0 and there is at least one free active counter
    if people_ahead == 0 and busy_counters < active_counters:
        est_wait = 0
        status_msg = "Next in line! A counter is ready for you."
    elif people_ahead == 0:
        # Next in line, but counters currently finishing previous users
        est_wait = max(1, round(dynamic_time * 0.4))
        status_msg = "You are next in line! Expected very shortly."
    else:
        # Multi-server queue formula: ceil((people_ahead / effective_counters) * dynamic_time)
        est_wait = math.ceil((people_ahead / effective_counters) * dynamic_time)
        status_msg = f"Approx. {est_wait} mins (~{people_ahead} {'person' if people_ahead == 1 else 'people'} ahead)"

    expected_turn_dt = datetime.now() + timedelta(minutes=est_wait)
    expected_turn_str = expected_turn_dt.strftime("%H:%M") if est_wait > 0 else "NOW"

    return {
        "service_id": service_id,
        "service_name": service["name"],
        "service_code": service["code"],
        "people_ahead": people_ahead,
        "active_counters": active_counters,
        "effective_counters": effective_counters,
        "dynamic_service_time": dynamic_time,
        "nominal_service_time": default_time,
        "estimated_wait_mins": est_wait,
        "expected_turn_time": expected_turn_str,
        "message": status_msg,
        "formula_breakdown": f"Wait = ⌈({people_ahead} ahead / {effective_counters} active counters) × {dynamic_time}m avg service⌉ = {est_wait} mins"
    }

def generate_next_token(conn, service_id, customer_name, customer_phone="", customer_email="", notes="", is_priority=0, token_type="REMOTE"):
    cursor = conn.cursor()
    cursor.execute("SELECT code, default_service_time FROM services WHERE id = ?", (service_id,))
    srv = cursor.fetchone()
    if not srv:
        raise ValueError("Invalid service ID")
    
    code = srv["code"]
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Find highest sequence today for this prefix
    cursor.execute("""
        SELECT token_number FROM tokens
        WHERE service_id = ? AND created_at >= ?
        ORDER BY id DESC LIMIT 1
    """, (service_id, today_str + " 00:00:00"))
    last_row = cursor.fetchone()
    
    if last_row and "-" in last_row["token_number"]:
        try:
            seq = int(last_row["token_number"].split("-")[-1]) + 1
        except Exception:
            seq = 101
    else:
        seq = 101

    token_number = f"{code}-{seq}"

    # Calculate initial estimated wait
    estimate = get_service_queue_estimate(cursor, service_id)
    est_wait = estimate["estimated_wait_mins"] if estimate else srv["default_service_time"]

    cursor.execute("""
        INSERT INTO tokens (token_number, service_id, customer_name, customer_phone, customer_email,
                            notes, is_priority, status, token_type, created_at, estimated_wait_mins)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'WAITING', ?, CURRENT_TIMESTAMP, ?)
    """, (token_number, service_id, customer_name, customer_phone, customer_email, notes, is_priority, token_type, est_wait))
    
    token_id = cursor.lastrowid
    conn.commit()

    return {
        "id": token_id,
        "token_number": token_number,
        "service_id": service_id,
        "customer_name": customer_name,
        "is_priority": is_priority,
        "estimated_wait_mins": est_wait,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def call_next_token(conn, counter_id, operator_name=None):
    """
    Operator calls the next customer in queue. Priority tickets go first, then oldest WAITING ticket.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM counters WHERE id = ?", (counter_id,))
    counter = cursor.fetchone()
    if not counter:
        raise ValueError("Counter not found")

    # If counter is already serving a token, complete or warn?
    if counter["current_token_id"]:
        # Operator wants to call next, so we auto-complete or mark previous
        cursor.execute("SELECT status FROM tokens WHERE id = ?", (counter["current_token_id"],))
        prev = cursor.fetchone()
        if prev and prev["status"] in ["CALLED", "SERVING"]:
            complete_token(conn, counter_id)

    # Find next eligible token for this counter's service
    service_id = counter["service_id"]
    cursor.execute("""
        SELECT * FROM tokens
        WHERE service_id = ? AND status = 'WAITING'
        ORDER BY is_priority DESC, created_at ASC
        LIMIT 1
    """, (service_id,))
    next_token = cursor.fetchone()

    if not next_token:
        # No waiting tokens for this specific service; check if counter can help any service?
        return None

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # Calculate actual wait time so far
    try:
        created_dt = datetime.strptime(next_token["created_at"], "%Y-%m-%d %H:%M:%S")
        actual_wait = round((now - created_dt).total_seconds() / 60.0, 1)
    except Exception:
        actual_wait = 0.0

    op_name = operator_name or counter["current_operator"] or "Staff"

    # Update token status to CALLED
    cursor.execute("""
        UPDATE tokens
        SET status = 'CALLED', counter_id = ?, operator_name = ?,
            called_at = ?, actual_wait_mins = ?
        WHERE id = ?
    """, (counter_id, op_name, now_str, actual_wait, next_token["id"]))

    # Update counter current_token_id
    cursor.execute("""
        UPDATE counters
        SET current_token_id = ?, current_operator = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (next_token["id"], op_name, counter_id))

    conn.commit()

    return {
        "token_id": next_token["id"],
        "token_number": next_token["token_number"],
        "service_id": service_id,
        "customer_name": next_token["customer_name"],
        "is_priority": next_token["is_priority"],
        "counter_id": counter_id,
        "counter_name": counter["name"],
        "operator_name": op_name,
        "called_at": now_str,
        "status": "CALLED"
    }

def start_serving_token(conn, counter_id):
    cursor = conn.cursor()
    cursor.execute("SELECT current_token_id FROM counters WHERE id = ?", (counter_id,))
    ctr = cursor.fetchone()
    if not ctr or not ctr["current_token_id"]:
        raise ValueError("No token currently called at this counter")
    
    token_id = ctr["current_token_id"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE tokens SET status = 'SERVING', started_at = ? WHERE id = ?", (now_str, token_id))
    conn.commit()

    cursor.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
    return dict(cursor.fetchone())

def complete_token(conn, counter_id, feedback_rating=5, notes=""):
    cursor = conn.cursor()
    cursor.execute("SELECT current_token_id FROM counters WHERE id = ?", (counter_id,))
    ctr = cursor.fetchone()
    if not ctr or not ctr["current_token_id"]:
        return None

    token_id = ctr["current_token_id"]
    cursor.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
    tok = cursor.fetchone()
    if not tok:
        cursor.execute("UPDATE counters SET current_token_id = NULL WHERE id = ?", (counter_id,))
        conn.commit()
        return None

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # Calculate actual service minutes
    start_time_str = tok["started_at"] or tok["called_at"] or now_str
    try:
        start_dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
        service_mins = max(0.5, round((now - start_dt).total_seconds() / 60.0, 1))
    except Exception:
        service_mins = 5.0

    cursor.execute("""
        UPDATE tokens
        SET status = 'COMPLETED', completed_at = ?, actual_service_mins = ?, feedback_rating = ?
        WHERE id = ?
    """, (now_str, service_mins, feedback_rating, token_id))

    cursor.execute("UPDATE counters SET current_token_id = NULL WHERE id = ?", (counter_id,))
    conn.commit()

    return {
        "token_id": token_id,
        "token_number": tok["token_number"],
        "counter_id": counter_id,
        "actual_service_mins": service_mins,
        "status": "COMPLETED"
    }

def skip_token(conn, counter_id, reason="No Show"):
    cursor = conn.cursor()
    cursor.execute("SELECT current_token_id FROM counters WHERE id = ?", (counter_id,))
    ctr = cursor.fetchone()
    if not ctr or not ctr["current_token_id"]:
        return None

    token_id = ctr["current_token_id"]
    cursor.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
    tok = cursor.fetchone()
    if not tok:
        cursor.execute("UPDATE counters SET current_token_id = NULL WHERE id = ?", (counter_id,))
        conn.commit()
        return None

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE tokens
        SET status = 'SKIPPED', completed_at = ?, notes = coalesce(notes, '') || ' [Skipped: ' || ? || ']'
        WHERE id = ?
    """, (now_str, reason, token_id))

    cursor.execute("UPDATE counters SET current_token_id = NULL WHERE id = ?", (counter_id,))
    conn.commit()

    return {
        "token_id": token_id,
        "token_number": tok["token_number"],
        "counter_id": counter_id,
        "status": "SKIPPED",
        "reason": reason
    }

def transfer_token(conn, token_id, target_service_id, reason="Transferred"):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
    tok = cursor.fetchone()
    if not tok:
        raise ValueError("Token not found")

    # If it was assigned to a counter, clear that counter
    if tok["counter_id"]:
        cursor.execute("UPDATE counters SET current_token_id = NULL WHERE id = ?", (tok["counter_id"],))

    # Recalculate wait time for target service
    est = get_service_queue_estimate(cursor, target_service_id)
    est_wait = est["estimated_wait_mins"] if est else 10

    note_addon = f" [Transferred from {tok['service_id']} to {target_service_id}: {reason}]"
    cursor.execute("""
        UPDATE tokens
        SET service_id = ?, status = 'WAITING', counter_id = NULL, operator_name = NULL,
            called_at = NULL, started_at = NULL, notes = coalesce(notes, '') || ?,
            estimated_wait_mins = ?
        WHERE id = ?
    """, (target_service_id, note_addon, est_wait, token_id))

    conn.commit()
    return {"token_id": token_id, "target_service_id": target_service_id, "status": "WAITING"}
