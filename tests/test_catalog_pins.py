"""The Library PIN Service: Operations, Driver and Customer portal entry.

Mike Zachary, 2026-09-13: drivers create their own PIN, no more than four characters, and
nobody assigns one; any held driver PIN opens the Driver portal; a customer's load number is their PIN; an Operations PIN is authorized by
Mike Zachary by voice or in the dialog box with Joe.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dispatch_library.catalog import CatalogRefusal, NotFound, SCHEMA_VERSION, open_library
from dispatch_library.catalog import pins as pins_module
from dispatch_library.models import RESERVED_SYSTEM_IDENTITIES

MIKE = "Mike Zachary"
RAY, RAY_ID = "Ray Vasquez", "DRV-0007"
DANA, DANA_ID = "Dana Cole", "DRV-0008"


@pytest.fixture
def lib(tmp_path):
    service = open_library(tmp_path / "catalog.db")
    yield service
    service.close()


@pytest.fixture
def pins(lib):
    return lib.pins


def ops(pins, name=MIKE, pin="7301", channel="DIALOG"):
    return pins.create_pin("Operations", name, pin, requested_by=MIKE, channel=channel)


class TestTheFourAnswers:
    def test_operations_driver_customer_and_denied(self, pins):
        ops(pins)
        pins.add_driver_pin("4418")
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)

        assert pins.validate("Operations", "7301", client_key="laptop").answer()["role"] == "Operations"
        driver = pins.validate("Driver", "4418", client_key="tablet").answer()
        assert (driver["result"], driver["role"], driver["display_name"]) == ("Authenticated", "Driver", "Drivers")
        customer = pins.validate("Customer", "8842193", client_key="xpo-browser").answer()
        assert (customer["result"], customer["role"], customer["display_name"]) == ("Authenticated", "Customer", "XPO Logistics")
        assert pins.validate("Customer", "0000000", client_key="xpo-browser").answer() == {"result": "Denied"}

    def test_a_pin_opens_only_its_own_portal(self, pins):
        pins.add_driver_pin("4418")
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

    def test_disabling_a_customer_closes_every_load_number(self, pins):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        pins.add_customer_load("XPO Logistics", "8842204", requested_by=MIKE)
        pins.set_enabled("Customer", "XPO Logistics", False, requested_by=MIKE)
        assert not any(pins.validate("Customer", n, client_key="c").authenticated for n in ("8842193", "8842204"))


class TestDriversEnterFourCharacters:
    """The PIN window opens, four characters, repeat, saved. Nothing else (Mike Zachary, 2026-09-13)."""

    def test_four_characters_are_held_and_open_the_driver_portal(self, pins):
        assert pins.add_driver_pin("q7 z4")["already_present"] is False
        answer = pins.validate("Driver", "Q7Z4", client_key="t").answer()
        assert (answer["result"], answer["role"], answer["display_name"]) == ("Authenticated", "Driver", "Drivers")
        created = next(e for e in pins.events() if e["action"] == "CREATE_PIN")
        assert created["channel"] == "DRIVER_PORTAL"

    @pytest.mark.parametrize("pin", ["12345", "123", "", "abcde"])
    def test_a_driver_pin_is_exactly_four_characters(self, pins, pin):
        with pytest.raises(CatalogRefusal, match="4 characters|at least 4"):
            pins.add_driver_pin(pin)

    def test_it_does_not_matter_who_holds_which(self, pins):
        pins.add_driver_pin("4418")
        pins.add_driver_pin("AB12")
        assert pins.add_driver_pin("4418")["already_present"] is True  # the same four characters again
        assert {pins.validate("Driver", p, client_key="t").identity_id for p in ("4418", "ab12")} == \
            {pins.identity("Driver", "Drivers")["identity_id"]}

    def test_nobody_assigns_a_driver_pin(self, pins):
        with pytest.raises(CatalogRefusal, match="PIN window"):
            pins.create_pin("Driver", "Ray Vasquez", "4418", requested_by=MIKE)
        pins.add_driver_pin("4418")
        with pytest.raises(CatalogRefusal, match="PIN window"):
            pins.reset_pin("Driver", "Drivers", "9926", requested_by=MIKE)

    def test_the_office_retires_one_or_closes_them_all(self, pins):
        pins.add_driver_pin("4418")
        pins.add_driver_pin("5520")
        pins.disable_pin("Driver", "4418", requested_by=MIKE)
        assert not pins.validate("Driver", "4418", client_key="t").authenticated
        assert pins.validate("Driver", "5520", client_key="t").authenticated
        pins.set_enabled("Driver", "Drivers", False, requested_by=MIKE)
        assert not pins.validate("Driver", "5520", client_key="t").authenticated
        pins.set_enabled("Driver", "Drivers", True, requested_by=MIKE)
        assert pins.validate("Driver", "5520", client_key="t").authenticated


class TestOperationsIsMikesToAuthorize:
    @pytest.mark.parametrize("channel", ["VOICE", "dialog"])
    def test_mike_by_voice_or_dialog(self, pins, channel):
        ops(pins, channel=channel)
        assert pins.validate("Operations", "7301", client_key="laptop").authenticated

    @pytest.mark.parametrize("channel", ["JOE", "CLI", "EMAIL", ""])
    def test_any_other_channel_is_refused(self, pins, channel):
        with pytest.raises(CatalogRefusal, match="authorized by Mike Zachary"):
            ops(pins, channel=channel)

    @pytest.mark.parametrize("who", ["Dana Cole", "Mike", "Michael Zachary"])
    def test_anyone_else_is_refused(self, pins, who):
        with pytest.raises(CatalogRefusal, match="authorized by Mike Zachary"):
            pins.create_pin("Operations", "Dana Cole", "7301", requested_by=who, channel="DIALOG")

    @pytest.mark.parametrize("who", sorted(RESERVED_SYSTEM_IDENTITIES) + ["Joe", "email helper", ""])
    def test_work_is_done_for_a_person_never_a_system(self, pins, who):
        with pytest.raises(CatalogRefusal):
            pins.create_pin("Operations", "Someone", "7301", requested_by=who, channel="DIALOG")

    def test_reset_disable_and_unlock_follow_the_same_rule(self, pins):
        ops(pins, name="Dana Cole")
        with pytest.raises(CatalogRefusal):
            pins.reset_pin("Operations", "Dana Cole", "9926", requested_by=MIKE, channel="JOE")
        with pytest.raises(CatalogRefusal):
            pins.set_enabled("Operations", "Dana Cole", False, requested_by="Dana Cole", channel="DIALOG")
        with pytest.raises(CatalogRefusal):
            pins.unlock("laptop", "Operations", requested_by=MIKE, channel="CLI")
        pins.reset_pin("Operations", "Dana Cole", "9926", requested_by=MIKE, channel="VOICE")
        assert not pins.validate("Operations", "7301", client_key="t").authenticated
        assert pins.validate("Operations", "9926", client_key="t").authenticated

    def test_a_second_pin_is_a_reset_and_two_people_cannot_share_one(self, pins):
        ops(pins)
        with pytest.raises(CatalogRefusal, match="reset it instead"):
            ops(pins, pin="5555")
        with pytest.raises(CatalogRefusal, match="already belongs"):
            ops(pins, name="Dana Cole")

    def test_short_pins_are_refused(self, pins):
        with pytest.raises(CatalogRefusal, match="at least 4"):
            ops(pins, pin="12")

    def test_unknown_users_are_named(self, pins):
        with pytest.raises(NotFound):
            pins.reset_pin("Operations", "Nobody", "1234", requested_by=MIKE, channel="DIALOG")


class TestLockout:
    def test_five_misses_lock_that_device_even_for_the_right_pin(self, pins):
        pins.add_driver_pin("4418")
        for guess in ("0001", "0002", "0003", "0004", "0005"):
            assert not pins.validate("Driver", guess, client_key="stranger").authenticated
        assert not pins.validate("Driver", "4418", client_key="stranger").authenticated, "locked"
        assert pins.validate("Driver", "4418", client_key="ray-tablet").authenticated, "other devices unaffected"
        assert "LOCKED" in [e["action"] for e in pins.events(20)]

    def test_the_lock_expires(self, pins, monkeypatch):
        pins.add_driver_pin("4418")
        for _ in range(5):
            pins.validate("Driver", "9999", client_key="d")
        later = datetime.now(timezone.utc) + pins_module.LOCKOUT + timedelta(seconds=1)
        monkeypatch.setattr(pins_module, "_now", lambda: later)
        assert pins.validate("Driver", "4418", client_key="d").authenticated

    def test_success_clears_the_count(self, pins):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        for _ in range(4):
            pins.validate("Customer", "9999999", client_key="d")
        assert pins.validate("Customer", "8842193", client_key="d").authenticated
        for _ in range(4):
            pins.validate("Customer", "9999999", client_key="d")
        assert pins.validate("Customer", "8842193", client_key="d").authenticated

    def test_unlock_by_a_person(self, pins):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        for _ in range(5):
            pins.validate("Customer", "9999999", client_key="d")
        pins.unlock("d", "Customer", requested_by=MIKE)
        assert pins.validate("Customer", "8842193", client_key="d").authenticated


class TestTheRecord:
    def test_no_pin_is_stored_in_the_clear(self, lib, pins, tmp_path):
        pins.add_customer_load("XPO Logistics", "8842193", requested_by=MIKE)
        pins.add_driver_pin("6197")
        ops(pins, pin="730155")
        pins.validate("Customer", "8842193", client_key="c")
        pins.validate("Driver", "6197", client_key="c")
        # Four digits turn up by chance in any file of hashes and timestamps, so the driver PIN
        # is looked for as a stored value in every table; the longer PINs in the raw file too.
        for table in ("pin_identity", "pin_credential", "pin_event", "pin_lockout"):
            for row in lib.connection.execute(f"SELECT * FROM {table}"):
                assert all(str(v).strip() != "6197" and "6197" not in str(v).split() for v in row), table
        lib.close()
        raw = b"".join(p.read_bytes() for p in tmp_path.iterdir() if p.name.startswith("catalog.db"))
        assert b"8842193" not in raw, "a load number (a Customer PIN) is readable in the catalog file"
        assert b"730155" not in raw, "an Operations PIN is readable in the catalog file"

    def test_events_name_the_person_and_are_permanent(self, lib, pins):
        ops(pins, channel="VOICE")
        pins.validate("Operations", "0000", client_key="t")
        events = pins.events()
        created = next(e for e in events if e["action"] == "CREATE_PIN")
        assert (created["actor"], created["channel"]) == (MIKE, "VOICE")
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
        ops(lib.pins)
        lib.close()

    def test_the_cli_across_processes(self, tmp_path):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent / "src"),
                   DISPATCH_LIBRARY_CATALOG=str(tmp_path / "catalog.db"))

        def cli(*args, expect=0):
            done = subprocess.run([sys.executable, "-m", "dispatch_library.catalog", *args], env=env,
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
            assert done.returncode == expect, done.stdout + done.stderr
            return json.loads(done.stdout)

        lib = open_library(tmp_path / "catalog.db")
        lib.pins.add_driver_pin("4418")
        lib.close()
        cli("pin-load", "XPO Logistics", "8842193", "--by", MIKE)
        assert cli("pin-validate", "driver", "4418")["role"] == "Driver"
        assert cli("pin-validate", "customer", "8842193")["display_name"] == "XPO Logistics"
        assert cli("pin-validate", "customer", "1111111", expect=1) == {"result": "Denied"}
        cli("pin-retire", "driver", "4418", "--by", MIKE)
        assert cli("pin-validate", "driver", "4418", expect=1) == {"result": "Denied"}
        assert "authorized by Mike Zachary" in cli("pin-enable", "operations", MIKE, "--by", MIKE, expect=1)["refused"]
        assert {u["display_name"] for u in cli("pin-users")} == {"Drivers", "XPO Logistics"}
