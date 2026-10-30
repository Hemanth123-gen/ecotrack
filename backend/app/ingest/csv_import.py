"""CSV import: tolerant of common header names and Indian date formats."""

import csv
import io
from datetime import date, datetime

from ..engine import FactorDB
from .preview import ImportItem, preview_item

MAX_ROWS = 1000

TEMPLATE = """date,activity,quantity,unit,description
2026-10-01,car_petrol,24,km,office commute
2026-10-01,electricity_grid,240,units,October electricity bill
2026-10-02,lpg,1,cylinder,
2026-10-03,chicken,500,g,dinner
2026-10-05,flight_domestic,1150,km,Mumbai to Delhi
"""

_HEADERS = {
    "key": "key", "activity": "key", "type": "key", "factor": "key", "category_key": "key",
    "quantity": "quantity", "amount": "quantity", "qty": "quantity", "value": "quantity",
    "unit": "unit", "units": "unit", "uom": "unit",
    "date": "occurred_on", "occurred_on": "occurred_on", "day": "occurred_on",
    "description": "description", "note": "description", "notes": "description", "comment": "description",
}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y")


class CsvImportError(ValueError):
    pass


def parse_date(value: str) -> date | str | None:
    """Return a date, or the original string so validation reports it, or None if blank."""
    v = value.strip()
    if not v:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return v


def parse_csv(text: str, region: str, factors: FactorDB) -> list[ImportItem]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise CsvImportError("The file is empty")
    mapping = {h: _HEADERS.get(h.strip().lower().replace(" ", "_")) for h in reader.fieldnames}
    missing = {"key", "quantity", "unit"} - set(mapping.values())
    if missing:
        raise CsvImportError(
            f"Missing column(s): {', '.join(sorted(missing))}. Expected headers like: date, activity, quantity, unit"
        )

    items = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            raise CsvImportError(f"Too many rows (max {MAX_ROWS})")
        raw = {mapping[h]: (v or "").strip() for h, v in row.items() if h in mapping and mapping[h]}
        if not any(raw.values()):
            continue  # blank line
        if "occurred_on" in raw:
            raw["occurred_on"] = parse_date(raw["occurred_on"])
        items.append(preview_item(raw, region, factors))
    return items
