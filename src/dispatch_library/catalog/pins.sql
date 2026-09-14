-- Library catalog, schema version 3: the Library PIN Service.
--
-- Direction from Mike Zachary, 2026-09-13: Library owns the records behind portal entry --
-- users, roles, PIN hashes, lockout counters, identity records -- inside the Library catalog.
-- No separate authentication database, subsystem or agent. Joe performs the work.
--
-- Three roles, fixed: OPERATIONS, DRIVER, CUSTOMER. A CUSTOMER identity is one customer
-- (XPO, Werner); each of its load numbers is a PIN that opens only that customer's view.
--
-- PINs are never stored. pin_hash is HMAC-SHA256 under the key in pin_service_key, so a PIN
-- can be found by its hash and a load number can belong to only one customer. A short PIN
-- cannot survive theft of this file under any hashing scheme; what protects it is that the
-- file stays on the truck, and the per-device lockout below.

CREATE TABLE pin_identity (
    identity_id   TEXT PRIMARY KEY CHECK (identity_id GLOB 'pinid_?*'),
    role          TEXT NOT NULL CHECK (role IN ('OPERATIONS','DRIVER','CUSTOMER')),
    display_name  TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    subject_ref   TEXT,
    status        TEXT NOT NULL DEFAULT 'ENABLED' CHECK (status IN ('ENABLED','DISABLED')),
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (role, display_name),
    CHECK (replace(replace(upper(trim(created_by)),' ','_'),'-','_') NOT IN
           ('INTELLIGENCE','PUBLISHER','LIBRARY','JOE','DISPATCH','SYSTEM','AUTOMATION','COMI','EMAIL_HELPER'))
);

CREATE TABLE pin_credential (
    credential_id TEXT PRIMARY KEY CHECK (credential_id GLOB 'pincred_?*'),
    identity_id   TEXT NOT NULL REFERENCES pin_identity (identity_id),
    role          TEXT NOT NULL CHECK (role IN ('OPERATIONS','DRIVER','CUSTOMER')),
    pin_hash      TEXT NOT NULL CHECK (length(pin_hash) = 64 AND pin_hash NOT GLOB '*[^0-9a-f]*'),
    label         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'ENABLED' CHECK (status IN ('ENABLED','DISABLED')),
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    -- One PIN, one identity, within a portal: a load number cannot open two customers.
    UNIQUE (role, pin_hash)
);

CREATE TRIGGER pin_credential_role_matches_identity
BEFORE INSERT ON pin_credential
WHEN NOT EXISTS (SELECT 1 FROM pin_identity i WHERE i.identity_id = NEW.identity_id AND i.role = NEW.role)
BEGIN
    SELECT RAISE(ABORT, 'a PIN belongs to an identity of the same role');
END;

-- Failed attempts, counted per device (client_key) and portal. PIN-only entry names no
-- account, so this is the only place a guesser can be slowed.
CREATE TABLE pin_lockout (
    client_key        TEXT    NOT NULL CHECK (length(trim(client_key)) > 0),
    portal_role       TEXT    NOT NULL CHECK (portal_role IN ('OPERATIONS','DRIVER','CUSTOMER')),
    failures          INTEGER NOT NULL DEFAULT 0 CHECK (failures >= 0),
    window_started_at TEXT,
    locked_until      TEXT,
    PRIMARY KEY (client_key, portal_role)
);

CREATE TABLE pin_event (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN
        ('CREATE_IDENTITY','CREATE_PIN','RESET_PIN','DISABLE_PIN','ENABLE','DISABLE','AUTHENTICATED','DENIED','LOCKED')),
    role        TEXT,
    identity_id TEXT,
    client_key  TEXT,
    actor       TEXT,
    channel     TEXT,
    detail      TEXT NOT NULL DEFAULT '',
    -- Administrative actions name the person they were done for; never a system.
    CHECK (action IN ('AUTHENTICATED','DENIED','LOCKED') OR (actor IS NOT NULL AND
           replace(replace(upper(trim(actor)),' ','_'),'-','_') NOT IN
           ('INTELLIGENCE','PUBLISHER','LIBRARY','JOE','DISPATCH','SYSTEM','AUTOMATION','COMI','EMAIL_HELPER')))
);

CREATE TRIGGER pin_event_is_append_only_update
BEFORE UPDATE ON pin_event
BEGIN
    SELECT RAISE(ABORT, 'PIN events are a record and are never edited');
END;

CREATE TRIGGER pin_event_is_append_only_delete
BEFORE DELETE ON pin_event
BEGIN
    SELECT RAISE(ABORT, 'PIN events are a record and are never deleted');
END;

CREATE TABLE pin_service_key (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    secret     BLOB    NOT NULL CHECK (length(secret) >= 32),
    created_at TEXT    NOT NULL
);
