"""The Library PIN Service: who may enter the Operations, Driver and Customer portals.

Direction from Mike Zachary, 2026-09-13. Library owns the records -- identities, roles, PIN
hashes, lockout counters -- in the Library catalog. Joe performs the work: creating, resetting,
enabling, disabling and validating. There is no separate authentication system.

A portal asks one question and gets one of four answers:

    validate("CUSTOMER", "8842193", client_key="192.168.8.21")
        -> PinResult(authenticated=True, role="Customer", display_name="XPO Logistics", ...)
        -> PinResult(authenticated=False)                        # Denied

Denied never says why. Wrong PIN, disabled user and locked device look the same to whoever is
guessing; the reason is in `pin_event`.

**Customers.** A Customer Load Number is a Mission Visibility Key (Dispatch playbook Section 4A,
2026-09-13) -- not a username, account, company login or organizational credential. Here a
Customer identity is one customer, and each of its load numbers is a key. The key is
mission-scoped: Dispatch opens only the mission whose Mission Record carries that load number.
The Library's part is saying the key is good and whose it is; a load number already held by
one customer is refused for another.

**Drivers.** Mike Zachary, 2026-09-13: the PIN window opens, the driver enters four characters
and repeats them, and they are saved; "No other information or verification is needed." The
characters are an open-sesame: any held driver PIN opens the Driver portal, and "it does not
matter who is assigned what." Level 1 Transport has five drivers. All driver PINs belong to one
identity, DRIVERS; the office can retire one (disable_pin) or close them all (set_enabled).
Like every PIN, it is kept only as an HMAC, never in the clear.

**Operations** PINs are authorized by Mike Zachary, by voice or in the dialog box with Joe, and
by no one else and no other way (Mike Zachary, 2026-09-13).

**Lockout.** Failures are counted per device and portal: MAX_FAILURES misses within WINDOW
lock that device out of that portal for LOCKOUT. A success clears the count.

Deliberately absent: OAuth, SSO, Microsoft identity, password rules, MFA, cloud, external
providers.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from dispatch_library.catalog.store import Catalog, CatalogRefusal, NotFound
from dispatch_library.models import is_reserved_identity

ROLES = {"OPERATIONS": "Operations", "DRIVER": "Driver", "CUSTOMER": "Customer"}
MIN_PIN_LENGTH = 4
DRIVER_PIN_LENGTH = 4
OPERATIONS_AUTHORITY = "Mike Zachary"
OPERATIONS_CHANNELS = ("VOICE", "DIALOG")
DRIVER_CHANNEL = "DRIVER_PORTAL"
DRIVERS = "Drivers"
DRIVER_ACTOR = "Driver at the PIN window"
MAX_FAILURES = 5
WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)
UNKNOWN_CLIENT = "unknown-client"


@dataclass(frozen=True)
class PinResult:
    authenticated: bool
    role: Optional[str] = None           # "Operations", "Driver", "Customer"
    identity_id: Optional[str] = None
    display_name: Optional[str] = None   # the customer, driver or operator this PIN belongs to
    subject_ref: Optional[str] = None    # e.g. the Dispatch driver_id or customer key

    def answer(self) -> Dict[str, Optional[str]]:
        """What a portal needs: Authenticated with a role and who, or Denied."""
        if not self.authenticated:
            return {"result": "Denied"}
        return {"result": "Authenticated", "role": self.role, "identity_id": self.identity_id,
                "display_name": self.display_name, "subject_ref": self.subject_ref}


DENIED = PinResult(authenticated=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def normalize_pin(pin: str) -> str:
    """Spaces removed, letters upper-cased: `xpo 8842 193` and `XPO8842193` are one PIN."""
    return "".join((pin or "").split()).upper()


def _role(role: str) -> str:
    key = (role or "").strip().upper()
    if key not in ROLES:
        raise CatalogRefusal(f"{role!r} is not a portal role; the roles are Operations, Driver and Customer")
    return key


class PinService:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.db = catalog.db

    # ── the key ──────────────────────────────────────────────────────────

    def _secret(self) -> bytes:
        row = self.db.execute("SELECT secret FROM pin_service_key WHERE id = 1").fetchone()
        if row is not None:
            return bytes(row["secret"])
        with self.catalog.write() as db:
            db.execute("INSERT OR IGNORE INTO pin_service_key (id, secret, created_at) VALUES (1, ?, ?)",
                       (secrets.token_bytes(32), _iso(_now())))
        return bytes(self.db.execute("SELECT secret FROM pin_service_key WHERE id = 1").fetchone()["secret"])

    def _hash(self, role: str, pin: str) -> str:
        return hmac.new(self._secret(), f"{role}:{normalize_pin(pin)}".encode("utf-8"), hashlib.sha256).hexdigest()

    # ── records ──────────────────────────────────────────────────────────

    def _person(self, requested_by: str) -> str:
        if not requested_by or not requested_by.strip() or is_reserved_identity(requested_by):
            raise CatalogRefusal(
                "PIN work is done for a named person; a system identity may not create, reset, enable or "
                "disable entry. Joe records the person he is acting for."
            )
        return requested_by.strip()

    def _authorized(self, role: str, requested_by: str, channel: str) -> str:
        """The person doing PIN work for this portal, or a refusal saying who may."""
        person = self._person(requested_by)
        if role == "OPERATIONS" and not (
                " ".join(person.split()).casefold() == OPERATIONS_AUTHORITY.casefold()
                and (channel or "").strip().upper() in OPERATIONS_CHANNELS):
            raise CatalogRefusal(
                f"an Operations PIN is authorized by {OPERATIONS_AUTHORITY}, by voice or in the dialog box "
                "with Joe, and by no one else"
            )
        return person

    def _event(self, db, action: str, *, role=None, identity_id=None, client_key=None, actor=None,
               channel=None, detail="") -> None:
        db.execute(
            "INSERT INTO pin_event (at, action, role, identity_id, client_key, actor, channel, detail) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (_iso(_now()), action, role, identity_id, client_key, actor, channel, detail),
        )

    def identity(self, role: str, display_name: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM pin_identity WHERE role = ? AND display_name = ?",
                              (_role(role), display_name.strip())).fetchone()
        return dict(row) if row else None

    def identities(self, role: Optional[str] = None) -> List[dict]:
        sql = ("SELECT i.*, (SELECT count(*) FROM pin_credential c WHERE c.identity_id = i.identity_id "
               "AND c.status = 'ENABLED') AS active_pins FROM pin_identity i")
        if role:
            return [dict(r) for r in self.db.execute(sql + " WHERE i.role = ? ORDER BY i.display_name", (_role(role),))]
        return [dict(r) for r in self.db.execute(sql + " ORDER BY i.role, i.display_name")]

    def _check_pin(self, pin: str, role: str = "") -> None:
        length = len(normalize_pin(pin))
        if length < MIN_PIN_LENGTH:
            raise CatalogRefusal(f"a PIN is at least {MIN_PIN_LENGTH} characters")
        if role == "DRIVER" and length != DRIVER_PIN_LENGTH:
            raise CatalogRefusal(f"a driver PIN is {DRIVER_PIN_LENGTH} characters")

    def _holder(self, role: str, pin_hash: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT c.credential_id, c.status AS pin_status, i.* FROM pin_credential c "
            "JOIN pin_identity i USING (identity_id) WHERE c.role = ? AND c.pin_hash = ?",
            (role, pin_hash),
        ).fetchone()
        return dict(row) if row else None

    def _ensure_identity(self, db, role: str, display_name: str, subject_ref: Optional[str], person: str,
                         channel: str) -> str:
        row = db.execute("SELECT identity_id FROM pin_identity WHERE role = ? AND display_name = ?",
                         (role, display_name)).fetchone()
        if row:
            return row["identity_id"]
        identity_id = f"pinid_{uuid.uuid4().hex}"
        now = _iso(_now())
        db.execute(
            "INSERT INTO pin_identity (identity_id, role, display_name, subject_ref, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (identity_id, role, display_name, subject_ref, person, now, now),
        )
        self._event(db, "CREATE_IDENTITY", role=role, identity_id=identity_id, actor=person, channel=channel,
                    detail=display_name)
        return identity_id

    def create_pin(self, role: str, display_name: str, pin: str, *, requested_by: str,
                   subject_ref: Optional[str] = None, label: str = "", channel: str = "JOE") -> dict:
        """Give an Operations user a PIN (creating the user if new), as authorized by Mike Zachary.

        An Operations user holds one PIN; use reset_pin to change it. Drivers choose their own
        (add_driver_pin); customers enter by load number (add_customer_load).
        """
        role = _role(role)
        if role == "DRIVER":
            raise CatalogRefusal("driver PINs are entered at the Driver portal's PIN window; nobody assigns one")
        if role == "CUSTOMER":
            raise CatalogRefusal("customer entry is by load number; use add_customer_load")
        person = self._authorized(role, requested_by, channel)
        self._check_pin(pin)
        name = display_name.strip()
        existing = self.identity(role, name)
        if existing and self._active_pins(existing["identity_id"]):
            raise CatalogRefusal(f"{name} already has a PIN; reset it instead")
        return self._add(role, name, pin, person=person, subject_ref=subject_ref, label=label, channel=channel,
                         action="CREATE_PIN")

    def add_customer_load(self, customer: str, load_number: str, *, requested_by: str,
                          subject_ref: Optional[str] = None, channel: str = "JOE") -> dict:
        """A customer load number becomes a PIN into that customer's view. Idempotent per customer."""
        person = self._person(requested_by)
        self._check_pin(load_number)
        name = customer.strip()
        holder = self._holder("CUSTOMER", self._hash("CUSTOMER", load_number))
        if holder is not None:
            if holder["display_name"] == name:
                return {"identity_id": holder["identity_id"], "credential_id": holder["credential_id"],
                        "already_present": True}
            raise CatalogRefusal(
                f"that load number already opens {holder['display_name']}'s view; it cannot "
                f"also open {name}'s. Check the load number before adding it."
            )
        # The load number is the PIN, so it is not written down: the label keeps only its last three
        # characters, enough for Joe to tell one customer load from another.
        return self._add("CUSTOMER", name, load_number, person=person, subject_ref=subject_ref,
                         label=f"Load …{normalize_pin(load_number)[-3:]}", channel=channel, action="CREATE_PIN")

    def _active_pins(self, identity_id: str) -> int:
        return self.db.execute("SELECT count(*) FROM pin_credential WHERE identity_id = ? AND status = 'ENABLED'",
                               (identity_id,)).fetchone()[0]

    def _add(self, role, name, pin, *, person, subject_ref, label, channel, action) -> dict:
        pin_hash = self._hash(role, pin)
        holder = self._holder(role, pin_hash)
        if holder is not None:
            raise CatalogRefusal(f"that PIN already belongs to someone in the {ROLES[role]} portal; choose another")
        with self.catalog.write() as db:
            identity_id = self._ensure_identity(db, role, name, subject_ref, person, channel)
            credential_id = f"pincred_{uuid.uuid4().hex}"
            now = _iso(_now())
            db.execute(
                "INSERT INTO pin_credential (credential_id, identity_id, role, pin_hash, label, created_by, created_at, "
                "updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (credential_id, identity_id, role, pin_hash, label, person, now, now),
            )
            self._event(db, action, role=role, identity_id=identity_id, actor=person, channel=channel, detail=label)
        return {"identity_id": identity_id, "credential_id": credential_id, "already_present": False}

    def reset_pin(self, role: str, display_name: str, new_pin: str, *, requested_by: str,
                  channel: str = "JOE") -> dict:
        """Replace an Operations or Driver user's PIN. The old one stops working at once."""
        role = _role(role)
        if role == "CUSTOMER":
            raise CatalogRefusal("customer entry is by load number; add or disable load numbers instead")
        if role == "DRIVER":
            raise CatalogRefusal("driver PINs are entered at the Driver portal's PIN window; retire one with disable_pin")
        person = self._authorized(role, requested_by, channel)
        self._check_pin(new_pin)
        found = self.identity(role, display_name)
        if found is None:
            raise NotFound(f"no {ROLES[role]} user named {display_name!r}")
        pin_hash = self._hash(role, new_pin)
        holder = self._holder(role, pin_hash)
        if holder is not None and holder["identity_id"] != found["identity_id"]:
            raise CatalogRefusal(f"that PIN already belongs to someone in the {ROLES[role]} portal; choose another")
        with self.catalog.write() as db:
            now = _iso(_now())
            db.execute("UPDATE pin_credential SET status = 'DISABLED', updated_at = ? WHERE identity_id = ?",
                       (now, found["identity_id"]))
            if holder is not None:
                db.execute("UPDATE pin_credential SET status = 'ENABLED', updated_at = ? WHERE credential_id = ?",
                           (now, holder["credential_id"]))
            else:
                db.execute(
                    "INSERT INTO pin_credential (credential_id, identity_id, role, pin_hash, created_by, created_at, "
                    "updated_at) VALUES (?,?,?,?,?,?,?)",
                    (f"pincred_{uuid.uuid4().hex}", found["identity_id"], role, pin_hash, person, now, now),
                )
            self._event(db, "RESET_PIN", role=role, identity_id=found["identity_id"], actor=person, channel=channel)
        return {"identity_id": found["identity_id"]}

    def set_enabled(self, role: str, display_name: str, enabled: bool, *, requested_by: str,
                    channel: str = "JOE") -> dict:
        """Enable or disable a user. A disabled user's PINs all stop working; nothing is deleted."""
        role = _role(role)
        person = self._authorized(role, requested_by, channel)
        found = self.identity(role, display_name)
        if found is None:
            raise NotFound(f"no {ROLES[role]} user named {display_name!r}")
        with self.catalog.write() as db:
            db.execute("UPDATE pin_identity SET status = ?, updated_at = ? WHERE identity_id = ?",
                       ("ENABLED" if enabled else "DISABLED", _iso(_now()), found["identity_id"]))
            self._event(db, "ENABLE" if enabled else "DISABLE", role=role, identity_id=found["identity_id"],
                        actor=person, channel=channel)
        return self.identity(role, display_name)

    def disable_pin(self, role: str, pin: str, *, requested_by: str, channel: str = "JOE") -> dict:
        """Stop one PIN -- a customer load number, or one driver PIN -- without disabling the user."""
        role = _role(role)
        person = self._authorized(role, requested_by, channel)
        holder = self._holder(role, self._hash(role, pin))
        if holder is None:
            raise NotFound("no such PIN in that portal")
        with self.catalog.write() as db:
            db.execute("UPDATE pin_credential SET status = 'DISABLED', updated_at = ? WHERE credential_id = ?",
                       (_iso(_now()), holder["credential_id"]))
            self._event(db, "DISABLE_PIN", role=role, identity_id=holder["identity_id"], actor=person,
                        channel=channel)
        return {"identity_id": holder["identity_id"], "display_name": holder["display_name"]}

    # ── drivers ──────────────────────────────────────────────────────────

    def add_driver_pin(self, pin: str, *, channel: str = DRIVER_CHANNEL) -> dict:
        """Hold four characters that open the Driver portal. Nothing else is asked or linked.

        Mike Zachary, 2026-09-13: the PIN window opens, the driver enters four characters and
        repeats them, and they are saved -- "No other information or verification is needed."
        Entering four characters that are already held changes nothing.
        """
        self._check_pin(pin, "DRIVER")
        pin_hash = self._hash("DRIVER", pin)
        holder = self._holder("DRIVER", pin_hash)
        if holder is not None:
            return {"identity_id": holder["identity_id"], "already_present": True}
        with self.catalog.write() as db:
            identity_id = self._ensure_identity(db, "DRIVER", DRIVERS, None, DRIVER_ACTOR, channel)
            db.execute(
                "INSERT INTO pin_credential (credential_id, identity_id, role, pin_hash, created_by, created_at, "
                "updated_at) VALUES (?,?,?,?,?,?,?)",
                (f"pincred_{uuid.uuid4().hex}", identity_id, "DRIVER", pin_hash, DRIVER_ACTOR, _iso(_now()), _iso(_now())),
            )
            self._event(db, "CREATE_PIN", role="DRIVER", identity_id=identity_id, actor=DRIVER_ACTOR,
                        channel=channel, detail="entered at the PIN window")
        return {"identity_id": identity_id, "already_present": False}

    # ── validation ───────────────────────────────────────────────────────

    def validate(self, portal_role: str, pin: str, *, client_key: Optional[str] = None) -> PinResult:
        """Authenticated with a role and who, or Denied. Never says why it denied."""
        try:
            role = _role(portal_role)
        except CatalogRefusal:
            return DENIED
        client = (client_key or "").strip() or UNKNOWN_CLIENT
        now = _now()
        # Hashed before the transaction: the first hash on a new catalog creates the key, which is a
        # write of its own and cannot nest inside the one below.
        pin_hash = self._hash(role, pin) if normalize_pin(pin) else None
        with self.catalog.write() as db:
            lock = db.execute("SELECT * FROM pin_lockout WHERE client_key = ? AND portal_role = ?",
                              (client, role)).fetchone()
            if lock and lock["locked_until"] and datetime.fromisoformat(lock["locked_until"]) > now:
                self._event(db, "LOCKED", role=role, client_key=client, detail="attempt while locked")
                return DENIED

            holder = self._holder(role, pin_hash) if pin_hash else None
            if holder and holder["pin_status"] == "ENABLED" and holder["status"] == "ENABLED":
                db.execute("DELETE FROM pin_lockout WHERE client_key = ? AND portal_role = ?", (client, role))
                self._event(db, "AUTHENTICATED", role=role, identity_id=holder["identity_id"], client_key=client)
                return PinResult(True, ROLES[role], holder["identity_id"], holder["display_name"], holder["subject_ref"])

            reason = ("no such PIN" if holder is None else
                      "user disabled" if holder["status"] != "ENABLED" else "PIN disabled")
            window_open = (lock and lock["window_started_at"]
                           and now - datetime.fromisoformat(lock["window_started_at"]) <= WINDOW)
            failures = (lock["failures"] + 1) if window_open else 1
            started = lock["window_started_at"] if window_open else _iso(now)
            locked_until = _iso(now + LOCKOUT) if failures >= MAX_FAILURES else None
            db.execute(
                "INSERT INTO pin_lockout (client_key, portal_role, failures, window_started_at, locked_until) "
                "VALUES (?,?,?,?,?) ON CONFLICT (client_key, portal_role) DO UPDATE SET failures = excluded.failures, "
                "window_started_at = excluded.window_started_at, locked_until = excluded.locked_until",
                (client, role, failures, started, locked_until),
            )
            self._event(db, "DENIED", role=role, identity_id=holder["identity_id"] if holder else None,
                        client_key=client, detail=reason)
            if locked_until:
                self._event(db, "LOCKED", role=role, client_key=client,
                            detail=f"{failures} failures; locked until {locked_until}")
            return DENIED

    def unlock(self, client_key: str, portal_role: str, *, requested_by: str, channel: str = "JOE") -> None:
        """Clear a device's lockout early, for the person who is locked out."""
        role = _role(portal_role)
        person = self._authorized(role, requested_by, channel)
        with self.catalog.write() as db:
            db.execute("DELETE FROM pin_lockout WHERE client_key = ? AND portal_role = ?", (client_key, role))
            self._event(db, "ENABLE", role=role, client_key=client_key, actor=person, channel=channel,
                        detail="lockout cleared")

    def events(self, limit: int = 50) -> List[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM pin_event ORDER BY event_id DESC LIMIT ?", (limit,))]


def open_pin_service(path: Optional[str] = None) -> "PinService":
    """The PIN Service over the Library catalog at `path`, or DISPATCH_LIBRARY_CATALOG."""
    from dispatch_library.catalog.connection import open_catalog

    target = path or os.environ.get("DISPATCH_LIBRARY_CATALOG", "").strip()
    if not target:
        raise CatalogRefusal("no Library catalog: pass a path or set DISPATCH_LIBRARY_CATALOG")
    return PinService(Catalog(open_catalog(target)))
