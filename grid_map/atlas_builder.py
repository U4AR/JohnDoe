from __future__ import annotations


def empty_atlas() -> dict:
    return {
        "schema_version": 1,
        "landmarks": [],
        "districts": [],
        "notes": [
            "Add fictional landmarks here as the board is named.",
            "Lookout parsing should prefer this file over free-form image inference when possible.",
        ],
    }

