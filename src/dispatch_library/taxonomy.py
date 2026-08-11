"""
Library taxonomy — the 15 collections defined in 04_DISPATCH_SYSTEM_RELATIONSHIP_MATRIX.md
Section 7. This is a closed set; no code in this repo may create a 16th collection without a
doctrine rewrite.
"""
from __future__ import annotations

COLLECTIONS = (
    "Constitution",
    "Process",
    "Operations",
    "Compliance",
    "Training",
    "Reference",
    "Templates",
    "Company",
    "Customer",
    "Broker",
    "Location_Intelligence",
    "Route_Intelligence",
    "Publisher_Parts",
    "Security",
    "Index",
)

COLLECTION_SET = set(COLLECTIONS)


def is_valid_collection(name: str) -> bool:
    return name in COLLECTION_SET


def require_valid_collection(name: str) -> None:
    if not is_valid_collection(name):
        raise ValueError(
            f"collection {name!r} is not one of the 15 Library collections: {sorted(COLLECTION_SET)}"
        )
