import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.engine import default_db
from app.ingest import CSV_TEMPLATE, CsvImportError, DocumentError, DocumentExtractor, parse_csv
from app.main import create_app

from .conftest import FakeClient, text

DB = default_db()


# --- CSV -----------------------------------------------------------------------

def test_template_parses_cleanly():
    items = parse_csv(CSV_TEMPLATE, "IN", DB)
    assert len(items) == 5 and all(i.error is None for i in items)
    assert items[1].kg_co2e == pytest.approx(240 * 0.716)
    assert items[3].quantity == 500 and items[3].unit == "g" and items[3].kg_co2e == pytest.approx(3.45)


def test_csv_header_aliases_labels_and_indian_dates():
    csv_text = "Date,Type,Amount,UOM,Notes\n05/10/2026,Petrol car,10,km,office\n\n06-10-2026,Metro rail,12,kms,\n"
    items = parse_csv(csv_text, "IN", DB)
    assert [(i.key, str(i.occurred_on)) for i in items] == [("car_petrol", "2026-10-05"), ("metro", "2026-10-06")]
    assert items[0].description == "office" and items[0].category == "transport"


def test_csv_row_errors_are_reported_not_raised():
    future = (date.today() + timedelta(days=3)).isoformat()
    csv_text = (
        "activity,quantity,unit,date\n"
        "teleport,1,km,\n"
        "car_petrol,lots,km,\n"
        "lpg,1,km,\n"
        f"rice,1,kg,{future}\n"
        "rice,1,kg,31/31/2026\n"
        "rice,1,kg,\n"
    )
    items = parse_csv(csv_text, "IN", DB)
    assert [bool(i.error) for i in items] == [True, True, True, True, True, False]
    assert "Did you mean" in items[0].error or "No emission factor" in items[0].error
    assert "Invalid quantity" in items[1].error
    assert "future" in items[3].error


def test_csv_missing_columns_and_empty_file():
    with pytest.raises(CsvImportError, match="unit"):
        parse_csv("activity,quantity\nrice,1\n", "IN", DB)
    with pytest.raises(CsvImportError):
        parse_csv("", "IN", DB)


def test_csv_handles_excel_bom():
    assert parse_csv("﻿activity,quantity,unit\nrice,1,kg\n", "IN", DB)[0].error is None


# --- Document extraction ---------------------------------------------------------

def extraction(**overrides):
    payload = {
        "document_type": "electricity_bill",
        "summary": "Electricity bill for October 2026.",
        "items": [{"key": "electricity_grid", "quantity": 240, "unit": "kWh", "occurred_on": "2026-10-28",
                   "description": "Oct electricity bill", "confidence": 0.95}],
        "warnings": [],
    }
    payload.update(overrides)
    return text(json.dumps(payload))


def test_extractor_previews_items_and_sends_file_with_schema():
    client = FakeClient(extraction())
    out = DocumentExtractor(client, "m", DB).extract(b"\x89PNG...", "image/png", "IN")
    assert out.document_type == "electricity_bill"
    assert out.items[0].kg_co2e == pytest.approx(240 * 0.716)
    assert out.warnings == []

    req = client.requests[0]
    assert req["contents"][0].inline_data.mime_type == "image/png"
    schema = req["config"].response_json_schema
    assert "car_petrol" in schema["properties"]["items"]["items"]["properties"]["key"]["enum"]
    assert req["config"].response_mime_type == "application/json"


def test_extractor_flags_low_confidence_and_invalid_items():
    client = FakeClient(extraction(items=[
        {"key": "flight_domestic", "quantity": 1150, "unit": "km", "confidence": 0.5},
        {"key": "lpg", "quantity": 1, "unit": "km", "confidence": 0.9},
    ], warnings=["Distance estimated"]))
    out = DocumentExtractor(client, "m", DB).extract(b"%PDF", "application/pdf", "IN")
    assert out.items[0].error is None and out.items[1].error
    assert any("low confidence" in w for w in out.warnings)


def test_extractor_rejects_bad_files_and_bad_output():
    ex = DocumentExtractor(FakeClient(text("not json")), "m", DB)
    with pytest.raises(DocumentError, match="Unsupported"):
        ex.extract(b"x", "text/plain", "IN")
    with pytest.raises(DocumentError, match="empty"):
        ex.extract(b"", "image/png", "IN")
    with pytest.raises(DocumentError, match="too large"):
        ex.extract(b"x" * (10 * 1024 * 1024 + 1), "image/png", "IN")
    with pytest.raises(DocumentError, match="structured"):
        ex.extract(b"x", "image/png", "IN")


# --- API -------------------------------------------------------------------------

@pytest.fixture
def api(store):
    return TestClient(create_app(store=store, extractor=DocumentExtractor(FakeClient(extraction()), "m", store.factors)))


@pytest.fixture
def uid(api):
    return api.post("/api/users", json={"name": "Asha"}).json()["id"]


def test_csv_upload_preview_then_batch_save(api, uid):
    r = api.post(f"/api/users/{uid}/import/csv", files={"file": ("a.csv", CSV_TEMPLATE.encode(), "text/csv")})
    body = r.json()
    assert r.status_code == 200 and body["valid_count"] == 5
    assert api.get(f"/api/users/{uid}/activities?days=366").json() == []  # preview saves nothing

    rows = [{k: i[k] for k in ("key", "quantity", "unit", "occurred_on", "description")} for i in body["items"]]
    saved = api.post(f"/api/users/{uid}/activities/batch", json={"activities": rows})
    assert saved.status_code == 201 and len(saved.json()) == 5


def test_batch_is_all_or_nothing(api, uid):
    r = api.post(f"/api/users/{uid}/activities/batch", json={"activities": [
        {"key": "rice", "quantity": 1, "unit": "kg"},
        {"key": "rice", "quantity": 1, "unit": "km"},
    ]})
    assert r.status_code == 400
    assert r.json()["detail"]["errors"][0]["index"] == 1
    assert api.get(f"/api/users/{uid}/activities").json() == []


def test_csv_upload_errors(api, uid):
    bad = api.post(f"/api/users/{uid}/import/csv", files={"file": ("a.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert bad.status_code == 400 and "Missing column" in bad.json()["detail"]
    cp1252 = "activity,quantity,unit,description\nrice,1,kg,caf\xe9\n".encode("cp1252")
    assert api.post(f"/api/users/{uid}/import/csv", files={"file": ("a.csv", cp1252, "text/csv")}).status_code == 200


def test_csv_template_download(api):
    r = api.get("/api/import/csv-template")
    assert r.status_code == 200 and r.text.startswith("date,activity") and "attachment" in r.headers["content-disposition"]


def test_document_upload(api, uid):
    r = api.post(f"/api/users/{uid}/import/document", files={"file": ("bill.png", b"\x89PNG", "image/png")})
    body = r.json()
    assert r.status_code == 200 and body["document_type"] == "electricity_bill" and body["valid_count"] == 1
    bad = api.post(f"/api/users/{uid}/import/document", files={"file": ("a.txt", b"hi", "text/plain")})
    assert bad.status_code == 400


def test_document_upload_disabled_without_key(store):
    api = TestClient(create_app(store=store))
    uid = api.post("/api/users", json={"name": "Asha"}).json()["id"]
    assert api.get("/api/health").json()["document_import_enabled"] is False
    r = api.post(f"/api/users/{uid}/import/document", files={"file": ("bill.png", b"\x89PNG", "image/png")})
    assert r.status_code == 503
