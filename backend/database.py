import sqlite3
import os
import json
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "queueless.db")

PRESETS = {
    "university": {
        "org_name": "Apex University Academic & Student Services",
        "announcement": "Welcome! Please have your Student ID and fee clearance forms ready at the counter.",
        "services": [
            {
                "id": "adm",
                "code": "ADM",
                "name": "Admissions & Registrations",
                "description": "Enrollment, course adds/drops, official transcripts & degree verification",
                "default_service_time": 10,
                "icon": "graduation-cap",
                "color": "#3b82f6"
            },
            {
                "id": "fin",
                "code": "FIN",
                "name": "Student Finance & Scholarships",
                "description": "Tuition fees, payment plans, loan processing & scholarship disbursements",
                "default_service_time": 8,
                "icon": "receipt",
                "color": "#10b981"
            },
            {
                "id": "it",
                "code": "IT",
                "name": "Campus IT & Student Portal Helpdesk",
                "description": "ID card encoding, Wi-Fi configuration, email resets & portal access",
                "default_service_time": 6,
                "icon": "laptop",
                "color": "#8b5cf6"
            },
            {
                "id": "counsel",
                "code": "CNS",
                "name": "Academic Advising & Counseling",
                "description": "Degree roadmaps, career counseling, credit transfers & graduation checks",
                "default_service_time": 15,
                "icon": "user-check",
                "color": "#f59e0b"
            }
        ],
        "counters": [
            {"id": "c1", "name": "Counter 1 - Admissions", "service_id": "adm", "is_active": 1, "current_operator": "Emma Watson"},
            {"id": "c2", "name": "Counter 2 - Transcripts & Records", "service_id": "adm", "is_active": 1, "current_operator": "Daniel Craig"},
            {"id": "c3", "name": "Counter 3 - Tuition & Cashier", "service_id": "fin", "is_active": 1, "current_operator": "Marcus Vance"},
            {"id": "c4", "name": "Counter 4 - Scholarships & Aid", "service_id": "fin", "is_active": 1, "current_operator": "Amina Patel"},
            {"id": "c5", "name": "Counter 5 - IT Desk", "service_id": "it", "is_active": 1, "current_operator": "Kevin Zhao"},
            {"id": "c6", "name": "Counter 6 - Academic Advising", "service_id": "counsel", "is_active": 1, "current_operator": "Dr. Sarah Lin"}
        ]
    },
    "clinic": {
        "org_name": "CityCare Multi-Specialty Clinic & Urgent Care",
        "announcement": "Patients with acute fever or breathing difficulty please notify triage nurse immediately.",
        "services": [
            {
                "id": "triage",
                "code": "TRG",
                "name": "General Triage & Vitals",
                "description": "Blood pressure, temperature, preliminary screening & intake assessment",
                "default_service_time": 5,
                "icon": "heart-pulse",
                "color": "#ef4444"
            },
            {
                "id": "gp",
                "code": "OPD",
                "name": "General Physician Consultation",
                "description": "Routine medical examination, prescription refills & diagnosis",
                "default_service_time": 12,
                "icon": "stethoscope",
                "color": "#3b82f6"
            },
            {
                "id": "pharma",
                "code": "RX",
                "name": "Pharmacy & Dispensing",
                "description": "Medication dispensing, dosage explanation & insurance approval",
                "default_service_time": 6,
                "icon": "pill",
                "color": "#10b981"
            },
            {
                "id": "pediatric",
                "code": "PED",
                "name": "Pediatrics & Child Care",
                "description": "Infant immunizations, growth monitoring & child wellness",
                "default_service_time": 15,
                "icon": "baby",
                "color": "#ec4899"
            }
        ],
        "counters": [
            {"id": "c1", "name": "Station A - Intake & Vitals", "service_id": "triage", "is_active": 1, "current_operator": "Nurse Joy"},
            {"id": "c2", "name": "Room 101 - Dr. Robert House", "service_id": "gp", "is_active": 1, "current_operator": "Dr. Robert House"},
            {"id": "c3", "name": "Room 102 - Dr. Allison Cameron", "service_id": "gp", "is_active": 1, "current_operator": "Dr. Allison Cameron"},
            {"id": "c4", "name": "Pharmacy Counter 1", "service_id": "pharma", "is_active": 1, "current_operator": "James Wilson, RPh"},
            {"id": "c5", "name": "Pediatrics Room 201", "service_id": "pediatric", "is_active": 1, "current_operator": "Dr. Lisa Cuddy"}
        ]
    },
    "library": {
        "org_name": "Metro Central University Library",
        "announcement": "Please observe silence in study zones. Return overdue materials before semester end.",
        "services": [
            {
                "id": "circulation",
                "code": "CIR",
                "name": "Circulation & Book Checkout",
                "description": "Book borrowing, returns, renewals & inter-library reservations",
                "default_service_time": 4,
                "icon": "book-open",
                "color": "#3b82f6"
            },
            {
                "id": "clearance",
                "code": "CLR",
                "name": "Student Clearance & Fine Payment",
                "description": "Semester no-dues certificate, lost book settlements & fine waivers",
                "default_service_time": 6,
                "icon": "check-circle",
                "color": "#10b981"
            },
            {
                "id": "archives",
                "code": "ARC",
                "name": "Special Collections & Theses Archive",
                "description": "Microfilm review, thesis deposition & rare manuscript access",
                "default_service_time": 12,
                "icon": "archive",
                "color": "#8b5cf6"
            }
        ],
        "counters": [
            {"id": "c1", "name": "Circulation Desk 1", "service_id": "circulation", "is_active": 1, "current_operator": "Eleanor Vance"},
            {"id": "c2", "name": "Circulation Desk 2", "service_id": "circulation", "is_active": 1, "current_operator": "Arthur Pendelton"},
            {"id": "c3", "name": "Clearance & Dues Desk", "service_id": "clearance", "is_active": 1, "current_operator": "Clara Oswald"},
            {"id": "c4", "name": "Rare Archive Reading Desk", "service_id": "archives", "is_active": 1, "current_operator": "Prof. Giles"}
        ]
    },
    "laboratory": {
        "org_name": "BioCare Diagnostic & Pathology Laboratories",
        "announcement": "Fast-track tokens available for fasting blood sugar & pregnant individuals.",
        "services": [
            {
                "id": "blood",
                "code": "BLD",
                "name": "Blood & Phlebotomy Collection",
                "description": "Fasting samples, CBC, lipid profile, metabolic panels & HbA1c",
                "default_service_time": 7,
                "icon": "flask-conical",
                "color": "#ef4444"
            },
            {
                "id": "imaging",
                "code": "IMG",
                "name": "X-Ray & Diagnostic Sonography",
                "description": "Chest radiographs, ultrasound scans, bone density & scans",
                "default_service_time": 15,
                "icon": "scan",
                "color": "#0ea5e9"
            },
            {
                "id": "reports",
                "code": "RPT",
                "name": "Report Dispatch & Doctor Consultation",
                "description": "Printed verified test reports, pathologist query & digital uploads",
                "default_service_time": 5,
                "icon": "file-text",
                "color": "#10b981"
            }
        ],
        "counters": [
            {"id": "c1", "name": "Phlebotomy Station 1", "service_id": "blood", "is_active": 1, "current_operator": "Technician Maya"},
            {"id": "c2", "name": "Phlebotomy Station 2", "service_id": "blood", "is_active": 1, "current_operator": "Technician Liam"},
            {"id": "c3", "name": "Radiology Suite 1", "service_id": "imaging", "is_active": 1, "current_operator": "Dr. Nathan Cross"},
            {"id": "c4", "name": "Report Collection Desk", "service_id": "reports", "is_active": 1, "current_operator": "Sofia Reyes"}
        ]
    }
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        default_service_time INTEGER NOT NULL DEFAULT 10,
        icon TEXT DEFAULT 'layers',
        color TEXT DEFAULT '#3b82f6',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS counters (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        service_id TEXT,
        is_active INTEGER DEFAULT 1,
        current_operator TEXT DEFAULT '',
        current_token_id INTEGER DEFAULT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(service_id) REFERENCES services(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_number TEXT UNIQUE NOT NULL,
        service_id TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT,
        customer_email TEXT,
        notes TEXT,
        is_priority INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'WAITING', -- WAITING, CALLED, SERVING, COMPLETED, SKIPPED, CANCELLED
        counter_id TEXT DEFAULT NULL,
        operator_name TEXT DEFAULT NULL,
        token_type TEXT DEFAULT 'REMOTE', -- REMOTE, WALK_IN, APPOINTMENT
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        called_at TIMESTAMP DEFAULT NULL,
        started_at TIMESTAMP DEFAULT NULL,
        completed_at TIMESTAMP DEFAULT NULL,
        estimated_wait_mins INTEGER DEFAULT 0,
        actual_wait_mins REAL DEFAULT 0,
        actual_service_mins REAL DEFAULT 0,
        feedback_rating INTEGER DEFAULT NULL,
        FOREIGN KEY(service_id) REFERENCES services(id),
        FOREIGN KEY(counter_id) REFERENCES counters(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_code TEXT UNIQUE NOT NULL,
        service_id TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT,
        customer_email TEXT,
        appointment_date TEXT NOT NULL,
        slot_time TEXT NOT NULL,
        notes TEXT,
        status TEXT DEFAULT 'CONFIRMED', -- CONFIRMED, CHECKED_IN, CANCELLED, NO_SHOW
        token_id INTEGER DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(service_id) REFERENCES services(id),
        FOREIGN KEY(token_id) REFERENCES tokens(id)
    )
    """)

    # Check if settings exists
    cursor.execute("SELECT value FROM settings WHERE key = 'active_preset'")
    row = cursor.fetchone()
    if not row:
        conn.commit()
        conn.close()
        load_preset("university", seed_sample_tokens=True)
    else:
        conn.commit()
        conn.close()

def load_preset(preset_key="university", seed_sample_tokens=True):
    if preset_key not in PRESETS:
        preset_key = "university"
    
    preset = PRESETS[preset_key]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('active_preset', ?)", (preset_key,))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('organization_name', ?)", (preset["org_name"],))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('announcement_banner', ?)", (preset["announcement"],))

    # Clear current counters, services, tokens, appointments
    cursor.execute("DELETE FROM counters")
    cursor.execute("DELETE FROM services")
    cursor.execute("DELETE FROM tokens")
    cursor.execute("DELETE FROM appointments")

    # Insert services
    for s in preset["services"]:
        cursor.execute("""
        INSERT INTO services (id, code, name, description, default_service_time, icon, color, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (s["id"], s["code"], s["name"], s["description"], s["default_service_time"], s["icon"], s["color"]))

    # Insert counters
    for c in preset["counters"]:
        cursor.execute("""
        INSERT INTO counters (id, name, service_id, is_active, current_operator, current_token_id)
        VALUES (?, ?, ?, ?, ?, NULL)
        """, (c["id"], c["name"], c["service_id"], c["is_active"], c["current_operator"]))

    conn.commit()

    if seed_sample_tokens:
        _seed_realistic_data(conn, preset)

    conn.close()

def _seed_realistic_data(conn, preset):
    cursor = conn.cursor()
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # Seed some completed tokens earlier today to give realistic analytics & service times
    sample_names = [
        ("Liam Patel", "+1-555-0101"),
        ("Sophia Ramirez", "+1-555-0102"),
        ("Jackson Lee", "+1-555-0103"),
        ("Olivia Chen", "+1-555-0104"),
        ("Noah Taylor", "+1-555-0105"),
        ("Ava Anderson", "+1-555-0106"),
        ("Lucas Thomas", "+1-555-0107"),
        ("Mia Hernandez", "+1-555-0108"),
        ("Ethan Wright", "+1-555-0109"),
        ("Isabella Martinez", "+1-555-0110"),
        ("Benjamin Scott", "+1-555-0111"),
        ("Charlotte King", "+1-555-0112"),
    ]

    services = preset["services"]
    counters = preset["counters"]

    # Seed 6 COMPLETED tokens
    for i in range(6):
        name, phone = sample_names[i]
        srv = services[i % len(services)]
        matching_counters = [c for c in counters if c["service_id"] == srv["id"]]
        ctr = matching_counters[0] if matching_counters else counters[0]
        token_num = f"{srv['code']}-{101 + i}"
        
        created_time = now - timedelta(minutes=60 - (i * 8))
        called_time = created_time + timedelta(minutes=6 + (i % 3))
        started_time = called_time + timedelta(seconds=20)
        dur = srv["default_service_time"] + (i % 3 - 1)
        completed_time = started_time + timedelta(minutes=dur)
        wait_mins = round((called_time - created_time).total_seconds() / 60.0, 1)

        cursor.execute("""
        INSERT INTO tokens (token_number, service_id, customer_name, customer_phone, is_priority,
                            status, counter_id, operator_name, token_type, created_at, called_at,
                            started_at, completed_at, estimated_wait_mins, actual_wait_mins, actual_service_mins, feedback_rating)
        VALUES (?, ?, ?, ?, ?, 'COMPLETED', ?, ?, 'WALK_IN', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (token_num, srv["id"], name, phone, 0, ctr["id"], ctr["current_operator"],
              created_time.strftime("%Y-%m-%d %H:%M:%S"), called_time.strftime("%Y-%m-%d %H:%M:%S"),
              started_time.strftime("%Y-%m-%d %H:%M:%S"), completed_time.strftime("%Y-%m-%d %H:%M:%S"),
              srv["default_service_time"], wait_mins, dur, 5))

    # Seed 2 SERVING tokens (currently in progress at counter 1 and counter 3)
    serving_samples = [
        (sample_names[6], services[0], counters[0], f"{services[0]['code']}-107"),
        (sample_names[7], services[1 % len(services)], counters[2 % len(counters)], f"{services[1 % len(services)]['code']}-108")
    ]
    for (name, phone), srv, ctr, token_num in serving_samples:
        created_time = now - timedelta(minutes=15)
        called_time = now - timedelta(minutes=5)
        started_time = now - timedelta(minutes=4)
        wait_mins = round((called_time - created_time).total_seconds() / 60.0, 1)

        cursor.execute("""
        INSERT INTO tokens (token_number, service_id, customer_name, customer_phone, is_priority,
                            status, counter_id, operator_name, token_type, created_at, called_at,
                            started_at, estimated_wait_mins, actual_wait_mins)
        VALUES (?, ?, ?, ?, 0, 'SERVING', ?, ?, 'REMOTE', ?, ?, ?, ?, ?)
        """, (token_num, srv["id"], name, phone, ctr["id"], ctr["current_operator"],
              created_time.strftime("%Y-%m-%d %H:%M:%S"), called_time.strftime("%Y-%m-%d %H:%M:%S"),
              started_time.strftime("%Y-%m-%d %H:%M:%S"), srv["default_service_time"], wait_mins))
        
        token_id = cursor.lastrowid
        cursor.execute("UPDATE counters SET current_token_id = ? WHERE id = ?", (token_id, ctr["id"]))

    # Seed 5 WAITING tokens (including one priority token)
    waiting_samples = [
        (sample_names[8], services[0], f"{services[0]['code']}-109", 1, "Elderly assistance / Fast-track requested"),
        (sample_names[9], services[0], f"{services[0]['code']}-110", 0, "Regular enrollment inquiry"),
        (sample_names[10], services[1 % len(services)], f"{services[1 % len(services)]['code']}-111", 0, "Fee clearance receipt needed"),
        (sample_names[11], services[2 % len(services)], f"{services[2 % len(services)]['code']}-112", 0, "ID badge configuration"),
        (("Daniel Kim", "+1-555-0113"), services[0], f"{services[0]['code']}-113", 0, "Transcript apostille")
    ]
    for i, ((name, phone), srv, token_num, is_prio, note) in enumerate(waiting_samples):
        created_time = now - timedelta(minutes=12 - i * 2)
        cursor.execute("""
        INSERT INTO tokens (token_number, service_id, customer_name, customer_phone, is_priority, notes,
                            status, token_type, created_at, estimated_wait_mins)
        VALUES (?, ?, ?, ?, ?, ?, 'WAITING', 'REMOTE', ?, ?)
        """, (token_num, srv["id"], name, phone, is_prio, note,
              created_time.strftime("%Y-%m-%d %H:%M:%S"), (i + 1) * srv["default_service_time"]))

    # Seed upcoming appointments for today and tomorrow
    slots = ["09:30 - 10:00", "10:30 - 11:00", "11:30 - 12:00", "14:00 - 14:30", "15:00 - 15:30"]
    apt_users = [
        ("Harper Davis", "+1-555-0201", "harper.d@example.com", services[0]["id"], today_str, slots[3]),
        ("Elijah Wood", "+1-555-0202", "ewood@example.com", services[1 % len(services)]["id"], today_str, slots[4]),
        ("Amelia Brooks", "+1-555-0203", "ambrooks@example.com", services[0]["id"], (now + timedelta(days=1)).strftime("%Y-%m-%d"), slots[1]),
        ("James Wilson", "+1-555-0204", "jwilson@example.com", services[2 % len(services)]["id"], (now + timedelta(days=1)).strftime("%Y-%m-%d"), slots[2]),
    ]

    for i, (name, phone, email, srv_id, apt_date, slot) in enumerate(apt_users):
        apt_code = f"APT-{1000 + i}"
        cursor.execute("""
        INSERT INTO appointments (appointment_code, service_id, customer_name, customer_phone, customer_email,
                                  appointment_date, slot_time, notes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Reserved online slot', 'CONFIRMED')
        """, (apt_code, srv_id, name, phone, email, apt_date, slot))

    conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
