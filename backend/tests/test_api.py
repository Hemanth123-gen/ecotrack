import pytest
from fastapi.testclient import TestClient

from app.agent import CarbonAgent
from app.main import create_app

from .conftest import FakeClient, fn_call, text


@pytest.fixture
def api(store):
    return TestClient(create_app(store=store, agent=None))


@pytest.fixture
def uid(api):
    r = api.post("/api/users", json={"name": "Asha"})
    assert r.status_code == 201
    return r.json()["id"]


def test_health_and_factors(api):
    assert api.get("/api/health").json()["status"] == "ok"
    keys = {f["key"] for f in api.get("/api/factors").json()}
    assert {"car_petrol", "electricity_grid"} <= keys


def test_activity_crud_and_summary(api, uid):
    r = api.post(f"/api/users/{uid}/activities", json={"key": "electricity_grid", "quantity": 100, "unit": "units"})
    assert r.status_code == 201 and r.json()["kg_co2e"] == pytest.approx(71.6)
    aid = r.json()["id"]

    assert len(api.get(f"/api/users/{uid}/activities").json()) == 1
    summary = api.get(f"/api/users/{uid}/summary?days=30").json()
    assert summary["total_kg_co2e"] == pytest.approx(71.6)
    recs = api.get(f"/api/users/{uid}/recommendations").json()["recommendations"]
    assert recs

    assert api.delete(f"/api/users/{uid}/activities/{aid}").status_code == 204
    assert api.delete(f"/api/users/{uid}/activities/{aid}").status_code == 400


def test_validation_errors(api, uid):
    assert api.post(f"/api/users/{uid}/activities", json={"key": "nope", "quantity": 1, "unit": "km"}).status_code == 400
    assert api.post(f"/api/users/{uid}/activities", json={"key": "lpg", "quantity": 1, "unit": "km"}).status_code == 400
    assert api.get("/api/users/missing/summary").status_code == 404


def test_chat_disabled_without_key(api, uid):
    r = api.post("/api/chat", json={"user_id": uid, "message": "hi"})
    assert r.status_code == 503


def test_chat_with_agent(store):
    client = FakeClient(
        fn_call("estimate_emissions", activities=[{"key": "flight_domestic", "quantity": 1150, "unit": "km"}]),
        text("About 172.5 kg CO2e."),
    )
    api = TestClient(create_app(store=store, agent=CarbonAgent(client, store, "m")))
    uid = api.post("/api/users", json={"name": "Asha"}).json()["id"]
    body = api.post("/api/chat", json={"user_id": uid, "message": "Flight Mumbai to Delhi?"}).json()
    assert body["reply"] == "About 172.5 kg CO2e."
    assert body["tool_calls"][0]["result"]["total_kg_co2e"] == pytest.approx(172.5)
    assert api.post("/api/chat", json={"user_id": "missing", "message": "hi"}).status_code == 404


def test_timeseries_is_zero_filled(api, uid):
    from datetime import date, timedelta

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    api.post(f"/api/users/{uid}/activities", json={"key": "car_petrol", "quantity": 10, "unit": "km", "occurred_on": yesterday})
    api.post(f"/api/users/{uid}/activities", json={"key": "chicken", "quantity": 1, "unit": "kg", "occurred_on": yesterday})
    points = api.get(f"/api/users/{uid}/timeseries?days=7").json()
    assert len(points) == 7
    assert points[-1]["date"] == date.today().isoformat() and points[-1]["total_kg_co2e"] == 0
    assert points[-2]["by_category"] == {"transport": pytest.approx(1.4), "food": pytest.approx(6.9)}


def test_concurrent_requests_share_one_connection_safely(api, uid):
    from concurrent.futures import ThreadPoolExecutor

    def log(i):
        return api.post(f"/api/users/{uid}/activities", json={"key": "rice", "quantity": 1, "unit": "kg"}).status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(log, range(64)))
    assert codes == [201] * 64
    assert len(api.get(f"/api/users/{uid}/activities").json()) == 64
