"""Unit normalisation so activities can be reported in any common unit."""


class UnitError(ValueError):
    pass


# canonical unit -> (dimension, multiplier to the dimension's base unit)
_UNITS: dict[str, tuple[str, float]] = {
    "km": ("distance", 1.0),
    "m": ("distance", 0.001),
    "mile": ("distance", 1.609344),
    "kwh": ("energy", 1.0),
    "mwh": ("energy", 1000.0),
    "litre": ("volume", 1.0),
    "ml": ("volume", 0.001),
    "gallon": ("volume", 3.78541),
    "kg": ("mass", 1.0),
    "g": ("mass", 0.001),
    "tonne": ("mass", 1000.0),
    "lpg_cylinder": ("mass", 14.2),  # standard Indian domestic LPG cylinder
    "scm": ("gas_volume", 1.0),
    "item": ("count", 1.0),
}

_ALIASES: dict[str, str] = {
    "kms": "km", "kilometre": "km", "kilometer": "km", "kilometres": "km", "kilometers": "km",
    "pkm": "km", "metre": "m", "meter": "m", "metres": "m", "meters": "m",
    "miles": "mile", "mi": "mile",
    "unit": "kwh", "units": "kwh",  # Indian electricity bills count kWh as "units"
    "l": "litre", "liter": "litre", "litres": "litre", "liters": "litre",
    "gallons": "gallon", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "gram": "g", "grams": "g", "gm": "g", "gms": "g",
    "t": "tonne", "tonnes": "tonne", "ton": "tonne", "tons": "tonne",
    "cylinder": "lpg_cylinder", "cylinders": "lpg_cylinder",
    "m3": "scm", "cubic_metre": "scm",
    "items": "item", "piece": "item", "pieces": "item", "pcs": "item",
}


def normalize_unit(unit: str) -> str:
    u = unit.strip().lower().replace(" ", "_")
    u = _ALIASES.get(u, u)
    if u not in _UNITS:
        raise UnitError(f"Unknown unit '{unit}'. Known units: {', '.join(sorted(_UNITS))}")
    return u


def dimension(unit: str) -> str:
    return _UNITS[normalize_unit(unit)][0]


def convert(quantity: float, from_unit: str, to_unit: str) -> float:
    src, dst = normalize_unit(from_unit), normalize_unit(to_unit)
    src_dim, src_mult = _UNITS[src]
    dst_dim, dst_mult = _UNITS[dst]
    if src_dim != dst_dim:
        raise UnitError(f"Cannot convert {from_unit} ({src_dim}) to {to_unit} ({dst_dim})")
    return quantity * src_mult / dst_mult
