"""The catalog schema is the approved plan, and it refuses what the plan says it refuses.

`schema_cases` holds every case of LIBRARY_IMPLEMENTATION_PLAN_v2 section 7.2 (run 2), executed
against `catalog/schema.sql`. A case named REFUSED must be refused by SQLite itself.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

import schema_cases
from dispatch_library.models import OBJECT_TYPES, RESERVED_SYSTEM_IDENTITIES
from dispatch_library.taxonomy import COLLECTIONS

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "LIBRARY_IMPLEMENTATION_PLAN_v2.md"


def _plan_block() -> str:
    text = PLAN.read_text(encoding="utf-8")
    end = "-- END CORRECTED SCHEMA v2"
    return text[text.index("-- BEGIN CORRECTED SCHEMA v2"):text.index(end) + len(end)]


def test_schema_file_is_the_approved_plan_verbatim():
    schema = schema_cases.SCHEMA
    block = _plan_block()
    assert block in schema, "catalog/schema.sql no longer matches LIBRARY_IMPLEMENTATION_PLAN_v2 section 2"


@pytest.mark.parametrize("status,name,detail", schema_cases.RESULTS, ids=[r[1] for r in schema_cases.RESULTS])
def test_schema_case(status, name, detail):
    assert status in ("REFUSED", "ACCEPTED"), detail


def test_case_counts_match_the_plan_record():
    refused = sum(r[0] == "REFUSED" for r in schema_cases.RESULTS)
    accepted = sum(r[0] == "ACCEPTED" for r in schema_cases.RESULTS)
    assert (refused, accepted) == (99, 22)


def test_shape_matches_the_plan_record():
    db = schema_cases.fresh()
    tables = db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    views = db.execute("SELECT count(*) FROM sqlite_master WHERE type='view'").fetchone()[0]
    triggers = db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
    assert (tables, views, triggers) == (19, 4, 34)


def test_seeded_collections_are_the_taxonomy():
    db = schema_cases.fresh()
    assert tuple(r[0] for r in db.execute("SELECT collection_id FROM library_collection ORDER BY rowid")) == COLLECTIONS


def test_every_refused_identity_list_is_the_python_constant():
    """Six CHECKs refuse system identities. Four carry exactly the nine (submitter name, reviewer,
    approver, archive decider); the object-type confirmer carries the nine plus HUMAN; the notice
    resolver carries the six that are never an authorised source. (Plan v2 section 7.2 said the
    nine-name list "appears in six CHECKs"; that sentence counted all six lists as the nine.)"""
    from dispatch_library.catalog.store import NOTICE_RESOLVER_REFUSED

    lists = [s for s in (set(re.findall(r"'([A-Z_]+)'", found)) for found in re.findall(
        r"NOT IN\s*\(((?:'[A-Z_]+',?)+)\)", schema_cases.SCHEMA)) if "SYSTEM" in s]
    nine = [s for s in lists if s == RESERVED_SYSTEM_IDENTITIES]
    assert len(nine) == 4
    assert RESERVED_SYSTEM_IDENTITIES | {"HUMAN"} in lists
    assert set(NOTICE_RESOLVER_REFUSED) in lists
    assert len(lists) == 6


def test_every_object_type_list_is_the_python_constant():
    lists = re.findall(r"IN \(\s*'CONSTITUTION_PACKAGE'.*?'LIBRARY_INDEX_MANIFEST'\)", schema_cases.SCHEMA, flags=re.S)
    assert len(lists) == 4
    for found in lists:
        assert tuple(re.findall(r"'([A-Z_]+)'", found)) == OBJECT_TYPES


def test_python_normalisation_matches_the_database():
    from dispatch_library.models import normalize_identity

    db = sqlite3.connect(":memory:")
    for name in (" publisher ", "Email Helper", "email-helper", "Joe Smith", "Mike Zachary", "COMI"):
        sql = db.execute("SELECT replace(replace(upper(trim(?)),' ','_'),'-','_')", (name,)).fetchone()[0]
        assert normalize_identity(name) == sql
