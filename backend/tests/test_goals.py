from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.agent import Toolbox
from app.engine import Activity, Goal, calculate_many, goal_progress, planned_t, weekly_insights
from app.engine.goals import trailing_pace
from app.main import create_app

TODAY = date(2026, 10, 30)


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def rice_kg(per_day: dict[int, float]):
    """Results for rice (4 kg CO2e per kg) on given days-ago -> kg of rice."""
    return calculate_many([
        Activity(key="rice", quantity=q, unit="kg", occurred_on=days_ago(n)) for n, q in per_day.items()
    ])


def daily_kg(results):
    out = {}
    for r in results:
        out[r.activity.occurred_on] = out.get(r.activity.occurred_on, 0) + r.kg_co2e
    return out


# --- pace & glide path ---------------------------------------------------------

def test_pace_needs_enough_days_and_uses_logged_span():
    assert trailing_pace(daily_kg(rice_kg({n: 1 for n in range(6)})), TODAY).t_per_year is None
    # 10 consecutive days of 4 kg -> 4 kg/day, not diluted over the 30-day window
    pace = trailing_pace(daily_kg(rice_kg({n: 1 for n in range(10)})), TODAY)
    assert pace.days_with_data == 10
    assert pace.t_per_year == pytest.approx(4 * 365 / 1000)


def test_planned_is_linear_and_clamped():
    g = Goal(baseline_t_per_year=4, target_t_per_year=2, start_date=days_ago(10), target_date=days_ago(-10))
    assert planned_t(g, days_ago(20)) == 4
    assert planned_t(g, TODAY) == pytest.approx(3)
    assert planned_t(g, days_ago(-30)) == 2


@pytest.mark.parametrize("kg_per_day, status", [(0.4, "achieved"), (0.7, "on_track"), (0.9, "behind")])
def test_goal_status(kg_per_day, status):
    # kg_per_day is kg of rice. Baseline 1.46 t/yr = 1 kg rice (4 kg CO2e) a day, target 0.73 t/yr;
    # halfway through, the planned pace is ~1.095 t/yr
    g = Goal(baseline_t_per_year=1.46, target_t_per_year=0.73, start_date=days_ago(30), target_date=days_ago(-30))
    p = goal_progress(g, rice_kg({n: kg_per_day for n in range(14)}), today=TODAY)
    assert p.status == status
    assert p.elapsed_pct == pytest.approx(50)
    assert p.days_left == 30


def test_goal_progress_details():
    g = Goal(baseline_t_per_year=1.46, target_t_per_year=0.73, start_date=days_ago(14), target_date=days_ago(-60))
    p = goal_progress(g, rice_kg({n: 0.75 for n in range(20)}), today=TODAY)
    assert p.reduction_achieved_pct == pytest.approx(50)  # 1.095 t/yr: half of the 0.73 t cut
    assert p.series[0].date <= g.start_date - timedelta(weeks=4) + timedelta(days=6)
    # history up to today has actual pace; the plan continues weekly to the target date
    past = [pt for pt in p.series if pt.date <= TODAY]
    assert past[-1].date == TODAY and past[-1].actual_t_per_year is not None
    assert all(pt.actual_t_per_year is None for pt in p.series if pt.date > TODAY)
    assert p.series[-1].date == g.target_date and p.series[-1].planned_t_per_year == g.target_t_per_year
    assert all(b.date - a.date <= timedelta(weeks=1) for a, b in zip(p.series, p.series[1:]))
    assert goal_progress(g, [], today=TODAY).status == "not_enough_data"


def test_logged_span_days():
    from app.engine import logged_span_days

    assert logged_span_days([], 30) == 30
    assert logged_span_days(rice_kg({n: 1 for n in range(14)}), 30, today=TODAY) == 14
    assert logged_span_days(rice_kg({0: 1}), 30, today=TODAY) == 7  # floored at a week
    assert logged_span_days(rice_kg({0: 1}), 5, today=TODAY) == 5  # but never beyond the window
    assert logged_span_days(rice_kg({40: 1, 2: 1}), 30, today=TODAY) == 30


# --- weekly insights -------------------------------------------------------------

def test_weekly_insights_compares_weeks():
    results = calculate_many(
        [Activity(key="car_petrol", quantity=20, unit="km", occurred_on=days_ago(n)) for n in range(7, 14)]  # last wk
        + [Activity(key="car_petrol", quantity=10, unit="km", occurred_on=days_ago(n)) for n in range(0, 5)]  # this wk
        + [Activity(key="electricity_grid", quantity=10, unit="kWh", occurred_on=days_ago(1))]
    )
    w = weekly_insights(results, today=TODAY)
    assert w.this_week_kg == pytest.approx(5 * 1.4 + 7.16)
    assert w.last_week_kg == pytest.approx(7 * 2.8)
    assert w.change_pct == pytest.approx((w.this_week_kg - w.last_week_kg) / w.last_week_kg * 100)
    assert w.days_logged_this_week == 5
    assert w.top_activity.key == "electricity_grid"
    text = " ".join(w.highlights)
    assert "Down" in text and "Biggest drop: Transport" in text and "Biggest rise: Energy" in text
    assert "5 of 7 days" in text


def test_weekly_insights_first_week_and_empty():
    first = weekly_insights(rice_kg({0: 1, 1: 1}), today=TODAY)
    assert first.change_pct is None and "Next week" in first.highlights[0]
    assert "Log more days" in first.highlights[-1]
    assert weekly_insights([], today=TODAY).highlights == ["Nothing logged in the last two weeks yet."]


# --- tools & API -------------------------------------------------------------------

def log_rice_days(store, uid, n_days, kg=1):
    for n in range(n_days):
        store.add_activity(uid, Activity(key="rice", quantity=kg, unit="kg",
                                         occurred_on=date.today() - timedelta(days=n)))


def test_set_goal_needs_baseline_data(store, user):
    t = Toolbox(store, user.id)
    future = (date.today() + timedelta(days=180)).isoformat()
    out = t.execute("set_goal", {"target_date": future, "reduction_pct": 20})
    assert "at least 7 days" in out["error"]
    # explicit baseline works without history
    ok = t.execute("set_goal", {"target_date": future, "reduction_pct": 20, "baseline_t_per_year": 3})
    assert ok["goal"]["target_t_per_year"] == pytest.approx(2.4)
    assert ok["status"] == "not_enough_data"


def test_set_goal_from_history_and_validation(store, user):
    log_rice_days(store, user.id, 10)
    t = Toolbox(store, user.id)
    future = (date.today() + timedelta(days=180)).isoformat()
    out = t.execute("set_goal", {"target_date": future, "reduction_pct": 25})
    assert out["goal"]["baseline_t_per_year"] == pytest.approx(1.46)
    assert out["goal"]["target_t_per_year"] == pytest.approx(1.095)
    assert out["status"] == "on_track"  # day 0: pace equals baseline equals the planned value

    assert "error" in t.execute("set_goal", {"target_date": future, "target_t_per_year": 5})
    assert "error" in t.execute("set_goal", {"target_date": "2020-01-01", "reduction_pct": 10})
    assert "error" in t.execute("set_goal", {"target_date": future})
    assert "error" in t.execute("set_goal", {"target_date": future, "reduction_pct": 10, "target_t_per_year": 1})


def test_goal_and_insights_api(store):
    api = TestClient(create_app(store=store))
    uid = api.post("/api/users", json={"name": "Asha"}).json()["id"]
    assert api.get(f"/api/users/{uid}/goal").json()["goal"] is None

    log_rice_days(store, uid, 8)
    future = (date.today() + timedelta(days=90)).isoformat()
    r = api.put(f"/api/users/{uid}/goal", json={"target_date": future, "reduction_pct": 10})
    assert r.status_code == 200 and r.json()["goal"]["target_date"] == future
    assert api.get(f"/api/users/{uid}/goal").json()["status"] in {"on_track", "behind", "achieved"}
    assert api.put(f"/api/users/{uid}/goal", json={"target_date": future, "reduction_pct": 150}).status_code == 422

    assert api.delete(f"/api/users/{uid}/goal").status_code == 204
    assert api.get(f"/api/users/{uid}/goal").json()["goal"] is None

    w = api.get(f"/api/users/{uid}/insights/weekly").json()
    assert w["days_logged_this_week"] == 7 and w["highlights"]


def test_simulate_api(store):
    api = TestClient(create_app(store=store))
    uid = api.post("/api/users", json={"name": "Asha"}).json()["id"]
    store.add_activity(uid, Activity(key="car_petrol", quantity=100, unit="km"))
    r = api.post(f"/api/users/{uid}/simulate", json={"kind": "switch", "from_key": "car_petrol", "to_key": "metro", "fraction": 1})
    assert r.status_code == 200 and r.json()["saved_kg"] == pytest.approx(100 * (0.14 - 0.015))
    bad = api.post(f"/api/users/{uid}/simulate", json={"kind": "switch", "from_key": "car_petrol", "to_key": "rice", "fraction": 1})
    assert bad.status_code == 400
