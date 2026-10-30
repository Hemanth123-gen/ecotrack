from datetime import date, timedelta

import pytest

from app.agent import CarbonAgent, Toolbox
from app.agent.prompt import build_system_prompt
from app.store import NotFound

from .conftest import FakeClient, fn_call, text


@pytest.fixture
def tools(store, user):
    return Toolbox(store, user.id)


# --- tools -------------------------------------------------------------------

def test_declarations_cover_all_tools(tools):
    names = {d.name for d in tools.declarations()}
    assert names == {
        "log_activities", "estimate_emissions", "get_footprint_summary", "list_recent_activities",
        "delete_activity", "simulate_scenario", "get_recommendations",
        "set_goal", "get_goal_progress", "get_weekly_insights",
    }
    assert all(d.description and d.parameters_json_schema for d in tools.declarations())


def test_log_activities_saves_and_reports_partial_errors(tools, store, user):
    out = tools.execute("log_activities", {"activities": [
        {"key": "car_petrol", "quantity": 20, "unit": "km", "description": "drive to office"},
        {"key": "teleport", "quantity": 1, "unit": "km"},
        {"key": "chicken", "quantity": 150, "unit": "g"},
    ]})
    assert [a["key"] for a in out["saved"]] == ["car_petrol", "chicken"]
    assert out["errors"][0]["input"]["key"] == "teleport"
    assert out["total_kg_co2e"] == pytest.approx(20 * 0.14 + 0.15 * 6.9, abs=1e-3)
    assert len(store.list_activities(user.id)) == 2
    assert out["saved"][0]["occurred_on"] == date.today().isoformat()


def test_estimate_does_not_save(tools, store, user):
    out = tools.execute("estimate_emissions", {"activities": [{"key": "flight_domestic", "quantity": 1150, "unit": "km"}]})
    assert out["total_kg_co2e"] == pytest.approx(172.5)
    assert store.list_activities(user.id) == []


def test_summary_and_recommendations(tools):
    tools.execute("log_activities", {"activities": [
        {"key": "electricity_grid", "quantity": 250, "unit": "units"},
        {"key": "car_petrol", "quantity": 600, "unit": "km"},
    ]})
    s = tools.execute("get_footprint_summary", {"days": 30})
    assert s["hotspots"][0]["key"] == "electricity_grid"
    assert s["days_with_data"] == 1 and s["activities_count"] == 2
    assert s["benchmarks"]
    recs = tools.execute("get_recommendations", {})["recommendations"]
    assert recs[0]["saved_kg_period"] >= recs[-1]["saved_kg_period"]


def test_summary_window_excludes_old_activities(tools):
    old = (date.today() - timedelta(days=40)).isoformat()
    tools.execute("log_activities", {"activities": [{"key": "car_petrol", "quantity": 100, "unit": "km", "occurred_on": old}]})
    assert tools.execute("get_footprint_summary", {"days": 30})["total_kg_co2e"] == 0
    assert tools.execute("get_footprint_summary", {"days": 60})["total_kg_co2e"] == pytest.approx(14)


def test_org_summary_has_scopes_but_no_benchmarks(store):
    org = store.create_user("Acme Pvt Ltd", kind="organization")
    t = Toolbox(store, org.id)
    t.execute("log_activities", {"activities": [
        {"key": "diesel_generator", "quantity": 100, "unit": "litre"},
        {"key": "electricity_grid", "quantity": 1, "unit": "MWh"},
    ]})
    s = t.execute("get_footprint_summary", {})
    assert s["benchmarks"] == []
    assert s["by_scope"] == {"1": pytest.approx(268), "2": pytest.approx(716)}


def test_simulate_scenario(tools):
    tools.execute("log_activities", {"activities": [{"key": "car_petrol", "quantity": 400, "unit": "km"}]})
    out = tools.execute("simulate_scenario", {"kind": "switch", "from_key": "car_petrol", "to_key": "metro", "fraction": 0.5})
    assert out["saved_kg"] == pytest.approx(200 * (0.14 - 0.015))
    assert "error" in tools.execute("simulate_scenario", {"kind": "switch", "from_key": "car_petrol", "fraction": 0.5})
    assert "error" in tools.execute("simulate_scenario", {"kind": "reduce", "from_key": "beef", "fraction": 0.5})


def test_delete_activity_only_for_owner(tools, store):
    saved = tools.execute("log_activities", {"activities": [{"key": "lpg", "quantity": 1, "unit": "cylinder"}]})["saved"][0]
    other = Toolbox(store, store.create_user("Ravi").id)
    assert "error" in other.execute("delete_activity", {"activity_id": saved["id"]})
    assert tools.execute("delete_activity", {"activity_id": saved["id"]}) == {"deleted": saved["id"]}
    assert tools.execute("list_recent_activities", {})["activities"] == []


def test_bad_tool_calls_return_errors(tools):
    assert "error" in tools.execute("nope", {})
    assert "error" in tools.execute("get_footprint_summary", {"bogus": 1})
    assert "error" in tools.execute("estimate_emissions", {"activities": [{"key": "car_petrol", "quantity": 1, "unit": "kg"}]})


# --- prompt ------------------------------------------------------------------

def test_prompt_contains_catalog_and_context(store, user):
    p = build_system_prompt(user, store.factors, today=date(2026, 10, 30))
    assert "2026-10-30" in p and "Asha" in p
    assert "- car_petrol - Petrol car [km, transport]" in p
    assert "NEVER calculate emissions yourself" in p


# --- agent loop --------------------------------------------------------------

def test_agent_calls_tool_then_answers(store, user):
    client = FakeClient(
        fn_call("log_activities", activities=[{"key": "car_petrol", "quantity": 20, "unit": "km"}]),
        text("Logged: 2.8 kg CO2e for your drive."),
    )
    reply = CarbonAgent(client, store, "test-model").chat(user.id, "I drove 20 km today")

    assert reply.reply == "Logged: 2.8 kg CO2e for your drive."
    assert [t.name for t in reply.tool_calls] == ["log_activities"]
    assert reply.tool_calls[0].result["total_kg_co2e"] == pytest.approx(2.8)
    assert len(store.list_activities(user.id)) == 1

    # the tool result was sent back to the model, tied to the call id
    fr = client.requests[1]["contents"][-1].parts[0].function_response
    assert fr.name == "log_activities" and fr.id == "call-log_activities"
    assert fr.response["total_kg_co2e"] == pytest.approx(2.8)
    assert client.requests[0]["model"] == "test-model"


def test_agent_persists_history_across_turns(store, user):
    client = FakeClient(text("Hi! What did you do today?"), text("Great question."))
    agent = CarbonAgent(client, store, "m")
    first = agent.chat(user.id, "hello")
    agent.chat(user.id, "what is CO2e?", first.conversation_id)

    second_request = client.requests[1]["contents"]
    assert [c.role for c in second_request] == ["user", "model", "user"]
    assert second_request[0].parts[0].text == "hello"


def test_agent_stops_after_max_steps(store, user):
    client = FakeClient(*[fn_call("list_recent_activities") for _ in range(3)])
    agent = CarbonAgent(client, store, "m", max_steps=3)
    reply = agent.chat(user.id, "loop forever")
    assert "couldn't finish" in reply.reply
    assert len(reply.tool_calls) == 3
    # history must end on a model turn so the next request is valid
    client.script = [text("ok")]
    agent.chat(user.id, "again", reply.conversation_id)
    assert client.requests[-1]["contents"][-2].role == "model"


def test_agent_rejects_other_users_conversation(store, user):
    agent = CarbonAgent(FakeClient(text("hi")), store, "m")
    conv = agent.chat(user.id, "hello").conversation_id
    other = store.create_user("Ravi")
    with pytest.raises(NotFound):
        agent.chat(other.id, "hi", conv)
