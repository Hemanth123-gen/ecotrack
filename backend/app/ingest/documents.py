"""Bill / receipt / ticket extraction with Gemini vision.

Gemini only reads quantities off the document; emissions are still computed by the engine, and the
user reviews the preview before anything is saved.
"""

import json
from datetime import date
from typing import Any

from google.genai import types
from pydantic import BaseModel

from ..engine import FactorDB
from .preview import ImportItem, preview_item

MAX_BYTES = 10 * 1024 * 1024
SUPPORTED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf",
}
DOCUMENT_TYPES = [
    "electricity_bill", "lpg_receipt", "piped_gas_bill", "fuel_receipt", "travel_ticket",
    "grocery_receipt", "shopping_receipt", "other", "unreadable",
]


class DocumentError(ValueError):
    pass


class DocumentExtraction(BaseModel):
    document_type: str
    summary: str
    items: list[ImportItem]
    warnings: list[str]


_INSTRUCTIONS = """You extract carbon-relevant activity quantities from a bill, receipt or ticket.
Today is {today}. Return JSON matching the schema. Use only factor keys from the enum.

Rules by document:
- Electricity bill: electricity_grid in kWh ("units") CONSUMED for the billing period - never the rupee amount.
  occurred_on = billing period end date (or bill date). With rooftop solar net metering use imported units.
- LPG receipt: lpg, unit "cylinder" (or kg if stated).
- Piped gas bill: png in scm consumed.
- Fuel receipt: petrol_fuel / diesel_fuel in litre, cng_fuel in kg.
- Travel ticket: flight_domestic / flight_international / train / bus with unit km. If the distance is not
  printed, estimate the great-circle (flights) or route (train/bus) distance between the stations, multiply
  by the number of passengers, set confidence <= 0.7, and add a warning saying the distance is estimated.
  Use one item per leg.
- Grocery receipt: food items converted to kg (or litre for milk), e.g. "Chicken 500g" -> 0.5 kg. Skip items
  with no matching factor and list them in a warning.
- Shopping receipt: smartphone, laptop, clothing_item as item counts.

General:
- Never invent quantities that are not on the document (estimated travel distance is the only exception).
- Dates as YYYY-MM-DD. Omit occurred_on if no date is visible.
- confidence: 1.0 when clearly printed, lower when blurry, ambiguous or estimated.
- description: a few words in plain language (e.g. "Oct electricity bill"). Do NOT copy names, addresses,
  phone numbers, account or consumer numbers into any field.
- summary: one sentence describing the document, without personal details.
- If the image is not a bill/receipt/ticket or is unreadable, use document_type "unreadable" or "other",
  return no items, and explain in warnings.
"""


def _schema(keys: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "document_type": {"type": "string", "enum": DOCUMENT_TYPES},
            "summary": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "enum": keys},
                        "quantity": {"type": "number"},
                        "unit": {"type": "string"},
                        "occurred_on": {"type": "string"},
                        "description": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["key", "quantity", "unit", "confidence"],
                },
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["document_type", "summary", "items", "warnings"],
    }


class DocumentExtractor:
    def __init__(self, client: Any, model: str, factors: FactorDB):
        self.client = client
        self.model = model
        self.factors = factors

    def extract(self, data: bytes, mime_type: str, region: str, today: date | None = None) -> DocumentExtraction:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise DocumentError(f"Unsupported file type '{mime_type}'. Upload a photo (JPEG/PNG/WebP/HEIC) or a PDF.")
        if not data:
            raise DocumentError("The file is empty")
        if len(data) > MAX_BYTES:
            raise DocumentError(f"File is too large (max {MAX_BYTES // (1024 * 1024)} MB)")

        catalog = "\n".join(f"- {f.key}: {f.label} [{f.unit}]" for f in self.factors.list(region))
        config = types.GenerateContentConfig(
            system_instruction=_INSTRUCTIONS.format(today=(today or date.today()).isoformat()),
            response_mime_type="application/json",
            response_json_schema=_schema(self.factors.keys()),
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=data, mime_type=mime_type),
                f"Factor catalog for region {region}:\n{catalog}\n\nExtract the activities from this document.",
            ],
            config=config,
        )
        try:
            raw = json.loads(response.text or "")
        except json.JSONDecodeError:
            raise DocumentError("Couldn't read a structured result from the model. Please try another photo.")

        items = [preview_item(item, region, self.factors) for item in raw.get("items", [])]
        warnings = [str(w) for w in raw.get("warnings", [])]
        if any(i.confidence is not None and i.confidence < 0.6 for i in items):
            warnings.append("Some values were read with low confidence - please check them before saving.")
        return DocumentExtraction(
            document_type=raw.get("document_type", "other"),
            summary=raw.get("summary", ""),
            items=items,
            warnings=warnings,
        )
