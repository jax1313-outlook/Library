"""The Library PIN Service: Operations, Driver and Customer portal entry."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dispatch_library.catalog import CatalogRefusal, NotFound, SCHEMA_VERSION, open_catalog, open_library
from dispatch_library.catalog import pins as pins_module
from dispatch_library.models import RESERVED_SYSTEM_IDENTITIES

MIKE = "Mike Zachary"


@pytest.fixture
def lib(tmp_path):
    service = open_library(tmp_path / "catalog.db")
    yield service
    service.close()


@pytest.fixture
def pins(lib):
    return lib.pins


class TestTheFourAnswers:
    def test_operations_driver_customer_and_denied(self, pins):
        pins.create_pin("Operations", MIKE, "7301", requested_by=MIKE)
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE, subject_ref="DRV-0007")
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)

        assert pins.validate("Operations", "7301", client_key="laptop").answer()["role"] == "Operations"
        driver = pins.validate("Driver", "4418", client_key="tablet").answer()
        assert (driver["result"], driver["role"], driver["subject_ref"]) == ("Authenticated", "Driver", "DRV-0007")
        customer = pins.validate("Customer", "8842193", client_key="xpo-browser").answer()
        assert (customer["result"], customer["role"], customer["display_name"]) == ("Authenticated", "Customer", "XPO Logistics")
        assert pins.validate("Customer", "0000000", client_key="xpo-browser").answer() == {"result": "Denied"}

    def test_a_pin_opens_only_its_own_portal(self, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        assert not pins.validate("Operations", "4418", client_key="tablet").authenticated
        assert not pins.validate("Customer", "4418", client_key="tablet").authenticated

    def test_an_unknown_portal_is_denied_not_an_error(self, pins):
        assert pins.validate("Admin", "7301").answer() == {"result": "Denied"}

    def test_spaces_and_case_do_not_matter(self, pins):
        pins.add_customer_load("Werner", "wer 5521 07", requested_by=MIKE)
        assert pins.validate("Customer", "WER552107", client_key="c").display_name == "Werner"


class TestCustomersAreKeptApart:
    def test_each_load_number_opens_only_its_customer(self, pins):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        pins.add_customer_load("XPO Logistics", "8842204", requested_by=MIKE)
        pins.add_customer_load("Werner", "5521907", requested_by=MIKE)
        assert pins.validate("Customer", "8842204", client_key="a").display_name == "XPO Logistics"
        assert pins.validate("Customer", "5521907", client_key="b").display_name == "Werner"
        xpo = pins.identity("Customer", "XPO Logistics")
        werner = pins.identity("Customer", "Werner")
        assert xpo["identity_id"] != werner["identity_id"]

    def test_a_load_number_cannot_belong_to_two_customers(self, pins):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        with pytest.raises(CatalogRefusal, match="already opens XPO Logistics"):
            pins.add_customer_load("Werner", "8842193", requested_by=MIKE)
        with pytest.raises(CatalogRefusal) as refused:
            pins.add_customer_load("Werner", "8842193", requested_by=MIKE)
        assert "8842193" not in str(refused.value), "a refusal must not repeat the PIN"
        assert pins.validate("Customer", "8842193", client_key="c").display_name == "XPO Logistics"

    def test_adding_the_same_load_twice_for_one_customer_is_harmless(self, pins):
        first = pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        again = pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        assert again["already_present"] is True and again["identity_id"] == first["identity_id"]

    def test_one_load_number_can_be_retired(self, pins):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        pins.add_customer_load("XPO Logistics", "8842204", requested_by=MIKE)
        pins.disable_pin("Customer", "8842193", requested_by=MIKE)
        assert not pins.validate("Customer", "8842193", client_key="c").authenticated
        assert pins.validate("Customer", "8842204", client_key="c").authenticated


class TestJoesWork:
    def test_reset_replaces_the_old_pin_immediately(self, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        pins.reset_pin("Driver", "Ray Vasquez", "9926", requested_by=MIKE)
        assert not pins.validate("Driver", "4418", client_key="t").authenticated
        assert pins.validate("Driver", "9926", client_key="t").authenticated

    def test_a_second_pin_for_a_driver_is_a_reset_not_a_create(self, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        with pytest.raises(CatalogRefusal, match="reset it instead"):
            pins.create_pin("Driver", "Ray Vasquez", "5555", requested_by=MIKE)

    def test_two_people_cannot_share_a_pin(self, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        with pytest.raises(CatalogRefusal, match="already belongs"):
            pins.create_pin("Driver", "Dana Cole", "4418", requested_by=MIKE)

    def test_disable_and_enable(self, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        pins.set_enabled("Driver", "Ray Vasquez", False, requested_by=MIKE)
        assert not pins.validate("Driver", "4418", client_key="t").authenticated
        pins.set_enabled("Driver", "Ray Vasquez", True, requested_by=MIKE)
        assert pins.validate("Driver", "4418", client_key="t").authenticated

    def test_disabling_a_customer_closes_every_load_number(self, pins):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        pins.add_customer_load("XPO Logistics", "8842204", requested_by=MIKE)
        pins.set_enabled("Customer", "XPO Logistics", False, requested_by=MIKE)
        assert not any(pins.validate("Customer", n, client_key="c").authenticated for n in ("8842193", "8842204"))

    @pytest.mark.parametrize("who", sorted(RESERVED_SYSTEM_IDENTITIES) + ["Joe", "email helper", ""])
    def test_work_is_done_for_a_person_never_a_system(self, pins, who):
        with pytest.raises(CatalogRefusal):
            pins.create_pin("Operations", "Someone", "7301", requested_by=who)

    def test_short_pins_are_refused(self, pins):
        with pytest.raises(CatalogRefusal, match="at least 4"):
            pins.create_pin("Driver", "Ray Vasquez", "12", requested_by=MIKE)

    def test_unknown_users_are_named(self, pins):
        with pytest.raises(NotFound):
            pins.reset_pin("Driver", "Nobody", "1234", requested_by=MIKE)


class TestLockout:
    def test_five_misses_lock_that_device_even_for_the_right_pin(self, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        for guess in ("0001", "0002", "0003", "0004", "0005"):
            assert not pins.validate("Driver", guess, client_key="stranger").authenticated
        assert not pins.validate("Driver", "4418", client_key="stranger").authenticated, "locked"
        assert pins.validate("Driver", "4418", client_key="ray-tablet").authenticated, "other devices unaffected"
        actions = [e["action"] for e in pins.events(20)]
        assert "LOCKED" in actions

    def test_the_lock_expires(self, pins, monkeypatch):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        for _ in range(5):
            pins.validate("Driver", "9999", client_key="d")
        later = datetime.now(timezone.utc) + pins_module.LOCKOUT + timedelta(seconds=1)
        monkeypatch.setattr(pins_module, "_now", lambda: later)
        assert pins.validate("Driver", "4418", client_key="d").authenticated

    def test_success_clears_the_count(self, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        for _ in range(4):
            pins.validate("Driver", "9999", client_key="d")
        assert pins.validate("Driver", "4418", client_key="d").authenticated
        for _ in range(4):
            pins.validate("Driver", "9999", client_key="d")
        assert pins.validate("Driver", "4418", client_key="d").authenticated

    def test_unlock_by_a_person(self, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        for _ in range(5):
            pins.validate("Driver", "9999", client_key="d")
        pins.unlock("d", "Driver", requested_by=MIKE)
        assert pins.validate("Driver", "4418", client_key="d").authenticated


class TestTheRecord:
    def test_no_pin_is_stored_in_the_clear(self, lib, pins, tmp_path):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        pins.create_pin("Driver", "Ray Vasquez", "44187", requested_by=MIKE)
        pins.validate("Customer", "8842193", client_key="c")
        lib.close()
        raw = b"".join(p.read_bytes() for p in tmp_path.iterdir() if p.name.startswith("catalog.db"))
        assert b"8842193" not in raw, "a load number (a Customer PIN) is readable in the catalog file"
        assert b"44187" not in raw, "a driver PIN is readable in the catalog file"

    def test_events_name_the_person_and_are_permanent(self, lib, pins):
        pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE, channel="JOE")
        pins.validate("Driver", "0000", client_key="t")
        events = pins.events()
        created = next(e for e in events if e["action"] == "CREATE_PIN")
        assert (created["actor"], created["channel"]) == (MIKE, "JOE")
        assert any(e["action"] == "DENIED" and e["detail"] == "no such PIN" for e in events)
        with pytest.raises(sqlite3.IntegrityError):
            lib.connection.execute("DELETE FROM pin_event")

    def test_the_database_refuses_a_system_as_creator(self, lib):
        with pytest.raises(sqlite3.IntegrityError):
            lib.connection.execute(
                "INSERT INTO pin_identity (identity_id, role, display_name, created_by, created_at, updated_at) "
                "VALUES ('pinid_x', 'DRIVER', 'x', 'Joe', 't', 't')")


class TestTheCatalog:
    def test_new_catalogs_are_version_three(self, lib):
        assert SCHEMA_VERSION == 3
        versions = [r[0] for r in lib.connection.execute("SELECT version FROM schema_version ORDER BY version")]
        assert versions == [2, 3]

    def test_a_version_two_catalog_gains_the_pin_tables_and_keeps_everything(self, tmp_path):
        from dispatch_library.catalog import connection

        path = tmp_path / "v2.db"
        db = connection.connect(path)
        db.execute("BEGIN IMMEDIATE")
        for statement in connection._statements(connection._SCHEMA_PATH.read_text(encoding="utf-8")):
            db.execute(statement)
        db.execute("INSERT INTO schema_version VALUES (2, 't', 'v2')")
        db.execute("COMMIT")
        db.close()

        lib = open_library(path)
        assert [r[0] for r in lib.connection.execute("SELECT version FROM schema_version ORDER BY version")] == [2, 3]
        assert lib.connection.execute("SELECT count(*) FROM library_collection").fetchone()[0] == 15
        lib.pins.create_pin("Operations", MIKE, "7301", requested_by=MIKE)
        lib.close()

    def test_the_cli_across_processes(self, tmp_path):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent / "src"),
                   DISPATCH_LIBRARY_CATALOG=str(tmp_path / "catalog.db"))

        def cli(*args, expect=0):
            done = subprocess.run([sys.executable, "-m", "dispatch_library.catalog", *args], env=env,
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
            assert done.returncode == expect, done.stdout + done.stderr
            return json.loads(done.stdout)

        cli("pin-create", "driver", "Ray Vasquez", "4418", "--by", MIKE)
        cli("pin-load", "XPO Logistics", "8842193", "--by", MIKE)
        assert cli("pin-validate", "driver", "4418")["role"] == "Driver"
        assert cli("pin-validate", "customer", "8842193")["display_name"] == "XPO Logistics"
        assert cli("pin-validate", "customer", "1111111", expect=1) == {"result": "Denied"}
        cli("pin-disable", "driver", "Ray Vasquez", "--by", MIKE)
        assert cli("pin-validate", "driver", "4418", expect=1) == {"result": "Denied"}
        assert {u["display_name"] for u in cli("pin-users")} == {"Ray Vasquez", "XPO Logistics"}
