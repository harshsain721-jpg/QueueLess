import asyncio
import os
import sys
from fastapi.testclient import TestClient

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.dirname(__file__))

import database
from app import app

client = TestClient(app)

def test_system_info():
    res = client.get("/api/info")
    assert res.status_code == 200
    data = res.json()
    assert "organization_name" in data
    assert "active_preset" in data
    print("PASS: /api/info verified:", data["organization_name"])

def test_services_and_wait_estimates():
    res = client.get("/api/services")
    assert res.status_code == 200
    services = res.json()
    assert len(services) > 0
    s0 = services[0]
    assert "estimated_wait_mins" in s0
    assert "dynamic_service_time" in s0
    assert "formula_breakdown" in s0
    print(f"PASS: /api/services verified ({len(services)} services). First service wait: ~{s0['estimated_wait_mins']} mins")

def test_take_token_and_queue_position():
    res_s = client.get("/api/services")
    s_id = res_s.json()[0]["id"]

    # Take a new remote token
    res = client.post("/api/tokens/take", json={
        "service_id": s_id,
        "customer_name": "Test User Alpha",
        "customer_phone": "+1-555-9999",
        "notes": "Testing token generation",
        "is_priority": 0,
        "token_type": "REMOTE"
    })
    assert res.status_code == 200
    token = res.json()
    token_num = token["token_number"]
    assert token_num is not None
    print(f"PASS: Token generated successfully: {token_num} for {token['customer_name']}")

    # Query token details and queue position
    res_details = client.get(f"/api/tokens/{token_num}")
    assert res_details.status_code == 200
    td = res_details.json()
    assert td["status"] == "WAITING"
    assert "estimate" in td
    assert td["estimate"]["people_ahead"] >= 0
    print(f"PASS: Token details query: {token_num} has {td['estimate']['people_ahead']} people ahead, expected turn: {td['estimate']['expected_turn_time']}")

def test_operator_lifecycle():
    # Find an active counter
    res_c = client.get("/api/counters")
    counters = res_c.json()
    assert len(counters) > 0
    ctr = counters[0]
    ctr_id = ctr["id"]

    # 1. Call next token
    res_call = client.post("/api/operator/call-next", json={
        "counter_id": ctr_id,
        "operator_name": "Test Operator"
    })
    assert res_call.status_code == 200
    called_data = res_call.json()
    print("PASS: Operator call-next result:", called_data.get("status") or called_data.get("token_number"))

    # 2. Recall token
    res_recall = client.post("/api/operator/recall", json={"counter_id": ctr_id})
    assert res_recall.status_code == 200
    print("PASS: Operator recall verified")

    # 3. Start serving
    res_start = client.post("/api/operator/start-serving", json={"counter_id": ctr_id})
    assert res_start.status_code == 200
    print("PASS: Operator start-serving verified")

    # 4. Complete token
    res_comp = client.post("/api/operator/complete", json={
        "counter_id": ctr_id,
        "feedback_rating": 5,
        "notes": "Fast efficient service"
    })
    assert res_comp.status_code == 200
    print("PASS: Operator complete verified")

def test_appointments_workflow():
    res_s = client.get("/api/services")
    s_id = res_s.json()[0]["id"]
    today_str = "2026-11-24"

    # 1. Available slots
    res_slots = client.get(f"/api/appointments/available-slots?service_id={s_id}&date_str={today_str}")
    assert res_slots.status_code == 200
    slots = res_slots.json()
    assert len(slots) > 0
    chosen_slot = slots[0]["slot_time"]
    print(f"PASS: Available slots query verified ({len(slots)} slots). Chosen: {chosen_slot}")

    # 2. Book appointment
    res_book = client.post("/api/appointments/book", json={
        "service_id": s_id,
        "customer_name": "Appointment VIP User",
        "customer_phone": "+1-555-8888",
        "customer_email": "vip@example.com",
        "appointment_date": today_str,
        "slot_time": chosen_slot,
        "notes": "Visa endorsement"
    })
    assert res_book.status_code == 200
    apt = res_book.json()
    apt_code = apt["appointment_code"]
    print(f"PASS: Appointment booked: {apt_code}")

    # 3. Check-in appointment
    res_checkin = client.post("/api/appointments/checkin", json={
        "appointment_code": apt_code
    })
    assert res_checkin.status_code == 200
    checkin_data = res_checkin.json()
    assert checkin_data["status"] == "CHECKED_IN"
    assert checkin_data["token"]["is_priority"] == 1
    print(f"PASS: Appointment check-in generated priority token: {checkin_data['token']['token_number']}")

def test_analytics_and_display_feed():
    res_a = client.get("/api/analytics")
    assert res_a.status_code == 200
    analytics = res_a.json()
    assert "summary" in analytics
    assert "hourly_distribution" in analytics
    assert "service_breakdown" in analytics
    assert "counter_efficiency" in analytics
    print(f"PASS: Analytics verified. Total today: {analytics['summary']['total_today']}, Avg Wait: {analytics['summary']['avg_wait_mins']}m")

    res_d = client.get("/api/display-feed")
    assert res_d.status_code == 200
    disp = res_d.json()
    assert "counters" in disp
    assert "up_next" in disp
    assert "recently_served" in disp
    print(f"PASS: Display feed verified ({len(disp['counters'])} counters, {len(disp['up_next'])} up next)")

def test_preset_switching():
    for preset in ["clinic", "library", "laboratory", "university"]:
        res = client.post("/api/admin/preset", json={"preset": preset, "seed_data": True})
        assert res.status_code == 200
        res_info = client.get("/api/info")
        assert res_info.json()["active_preset"] == preset
        print(f"PASS: Switched to preset '{preset}' successfully")

if __name__ == "__main__":
    print("\n--- Running QueueLess Automated Integration Tests ---")
    test_system_info()
    test_services_and_wait_estimates()
    test_take_token_and_queue_position()
    test_operator_lifecycle()
    test_appointments_workflow()
    test_analytics_and_display_feed()
    test_preset_switching()
    print("\nALL INTEGRATION TESTS PASSED PERFECTLY!\n")
