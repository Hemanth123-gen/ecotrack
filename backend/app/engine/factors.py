"""Emission factor database: loads vetted factors and resolves them by region."""

import difflib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

Category = Literal["transport", "energy", "food", "goods", "waste"]

DEFAULT_FACTORS_PATH = Path(__file__).resolve().parents[2] / "data" / "emission_factors.json"
GLOBAL = "GLOBAL"


class FactorNotFound(KeyError):
    pass


class EmissionFactor(BaseModel):
    key: str
    label: str
    category: Category
    scope: Literal[1, 2, 3]  # GHG Protocol scope, used for organisation reporting
    unit: str
    value: float  # kg CO2e per one `unit`
    region: str = GLOBAL
    source: str


class FactorDB:
    def __init__(self, factors: list[EmissionFactor], version: str = "unknown"):
        self.version = version
        self._index = {(f.key, f.region.upper()): f for f in factors}
        self._keys = sorted({f.key for f in factors})

    @classmethod
    def from_file(cls, path: Path = DEFAULT_FACTORS_PATH) -> "FactorDB":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([EmissionFactor(**f) for f in raw["factors"]], raw.get("version", "unknown"))

    def get(self, key: str, region: str = "IN") -> EmissionFactor:
        """Return the region-specific factor, falling back to the GLOBAL one."""
        for r in (region.upper(), GLOBAL):
            if (key, r) in self._index:
                return self._index[(key, r)]
        hint = difflib.get_close_matches(key, self._keys, n=3)
        raise FactorNotFound(
            f"No emission factor for '{key}'" + (f". Did you mean: {', '.join(hint)}?" if hint else "")
        )

    def keys(self) -> list[str]:
        return list(self._keys)

    def list(self, region: str = "IN", category: Category | None = None) -> list[EmissionFactor]:
        """One resolved factor per key for the given region."""
        resolved = [self.get(k, region) for k in self._keys]
        return [f for f in resolved if category is None or f.category == category]


@lru_cache(maxsize=1)
def default_db() -> FactorDB:
    return FactorDB.from_file()
