"""`python -m dispatch_library.catalog` -- the Library catalog from a command line.

Each invocation is a separate process that opens the catalog, does one thing, prints JSON, and
exits. That is the point: anything these commands show survived the process that wrote it.

The catalog is `--catalog PATH` or `DISPATCH_LIBRARY_CATALOG`; the shelf is `--memory-root` or
`DISPATCH_MEMORY_ROOT`. Nothing here writes to the shelf.

    status | init
    place --code --collection --title --type --accepted-by (--body | --body-file | --path) [--tag] [--capture-channel] [--minor]
    current CODE [--external] [--consumer ROLE] | history CODE | list [--collection]
    lifecycle CODE STATE
    submit --json FILE | candidates [--status S] | classify ID TYPE | confirm-type ID TYPE --by NAME
    validate ID | decide ID {approve,reject,defer} --by NAME [--capture-channel]
    notices [--status S] | resolve-notice ID --by NAME --resolution TEXT
    recipes-load [PATH] | recipe TYPE | resolve-packet TYPE
    scan [--dry-run]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sqlite3
import sys
from pathlib import Path

from dispatch_library.catalog.connection import SCHEMA_VERSION, current_version, sqlite_version
from dispatch_library.catalog.service import CATALOG_ENV, MEMORY_ENV, open_library
from dispatch_library.catalog.store import CatalogRefusal, NotFound
from dispatch_library.models import LibraryCandidate


def _jsonable(value):
    if dataclasses.is_dataclass(value):
        return value.to_dict()
    if isinstance(value, sqlite3.Row):
        return dict(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return getattr(value, "value", value)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m dispatch_library.catalog")
    p.add_argument("--catalog", default=os.environ.get(CATALOG_ENV, ""))
    p.add_argument("--memory-root", default=os.environ.get(MEMORY_ENV, ""))
    p.add_argument("--consumer", default="LIBRARY_CLI")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("init")
    place = sub.add_parser("place")
    for name in ("--code", "--collection", "--title", "--accepted-by"):
        place.add_argument(name, required=True)
    place.add_argument("--type")
    group = place.add_mutually_exclusive_group(required=True)
    group.add_argument("--body")
    group.add_argument("--body-file")
    group.add_argument("--path")
    place.add_argument("--tag", action="append", default=[])
    place.add_argument("--capture-channel")
    place.add_argument("--capture-ref")
    place.add_argument("--minor", action="store_true")
    place.add_argument("--review-due-date")
    current = sub.add_parser("current")
    current.add_argument("code")
    current.add_argument("--external", action="store_true")
    sub.add_parser("history").add_argument("code")
    sub.add_parser("list").add_argument("--collection")
    lifecycle = sub.add_parser("lifecycle")
    lifecycle.add_argument("code")
    lifecycle.add_argument("state")
    lifecycle.add_argument("--by", help="the person renewing an asset that is REVIEW_DUE")
    sub.add_parser("submit").add_argument("--json", required=True)
    sub.add_parser("candidates").add_argument("--status", action="append")
    classify = sub.add_parser("classify")
    classify.add_argument("id")
    classify.add_argument("type")
    confirm = sub.add_parser("confirm-type")
    confirm.add_argument("id")
    confirm.add_argument("type")
    confirm.add_argument("--by", required=True)
    sub.add_parser("validate").add_argument("id")
    decide = sub.add_parser("decide")
    decide.add_argument("id")
    decide.add_argument("decision", choices=("approve", "reject", "defer"))
    decide.add_argument("--by", required=True)
    decide.add_argument("--capture-channel")
    sub.add_parser("notices").add_argument("--status", default="OPEN")
    resolve = sub.add_parser("resolve-notice")
    resolve.add_argument("id")
    resolve.add_argument("--by", required=True)
    resolve.add_argument("--resolution", required=True)
    sub.add_parser("recipes-load").add_argument("path", nargs="?", default=r"D:\Library\publisher_recipes.json")
    sub.add_parser("recipe").add_argument("type")
    sub.add_parser("resolve-packet").add_argument("type")
    sub.add_parser("scan").add_argument("--dry-run", action="store_true")
    return p


def run(argv) -> tuple:
    args = _parser().parse_args(argv)
    if not args.catalog:
        return 2, {"error": f"no catalog: pass --catalog or set {CATALOG_ENV}"}
    lib = open_library(args.catalog, memory_root=args.memory_root or None, consumer_role=args.consumer)
    try:
        c = args.command
        if c in ("status", "init"):
            return 0, {
                "catalog": str(Path(args.catalog).resolve()),
                "sqlite": ".".join(map(str, sqlite_version())),
                "schema_version": current_version(lib.connection),
                "expected_schema_version": SCHEMA_VERSION,
                "journal_mode": lib.connection.execute("PRAGMA journal_mode").fetchone()[0],
                "memory_root": args.memory_root or None,
                "counts": lib.catalog.counts(),
            }
        if c == "place":
            body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
            row = lib.catalog.place(
                object_code=args.code, collection=args.collection, title=args.title, accepted_by=args.accepted_by,
                object_type=args.type, body=body, relative_path=args.path, tags=args.tag, minor=args.minor,
                capture_channel=args.capture_channel, capture_ref=args.capture_ref,
                review_due_date=args.review_due_date,
            )
            return 0, lib._object(row)
        if c == "current":
            obj = lib.current_for_external_use(args.code) if args.external else lib.current(args.code)
            return (0, obj) if obj is not None else (1, {"object_code": args.code, "outcome": "MISSING or BLOCKED"})
        if c == "history":
            return 0, lib.history(args.code)
        if c == "list":
            return 0, lib.list_current(args.collection)
        if c == "lifecycle":
            return 0, lib.set_lifecycle(args.code, args.state, by=args.by)
        if c == "submit":
            data = json.loads(Path(args.json).read_text(encoding="utf-8"))
            # source_refs ride beside the contract fields: [["WORKSPACE", "ws-1"], ...]. The shared
            # LibraryCandidate has no field for them, and the source trace check needs one.
            refs = data.pop("source_refs", [])
            candidate = lib.submit_candidate(LibraryCandidate(**data))
            for kind, reference in refs:
                lib.catalog.add_source_ref(kind, reference, candidate_id=candidate.candidate_id)
            return 0, candidate
        if c == "candidates":
            rows = lib.catalog.candidates(args.status)
            return 0, [dict(r) for r in rows]
        if c == "classify":
            return 0, lib.classify_candidate(args.id, args.type)
        if c == "confirm-type":
            return 0, lib.confirm_object_type(args.id, args.type, args.by)
        if c == "validate":
            result = lib.validate_candidate(args.id)
            return (0 if result["passed"] else 1), result
        if c == "decide":
            decision = {"approve": "APPROVED", "reject": "REJECTED", "defer": "DEFERRED"}[args.decision]
            row = lib.catalog.decide_candidate(args.id, decision, args.by, capture_channel=args.capture_channel)
            return 0, dict(row)
        if c == "notices":
            return 0, lib.notices(None if args.status == "ALL" else args.status)
        if c == "resolve-notice":
            return 0, lib.resolve_notice(args.id, args.by, args.resolution)
        if c == "recipes-load":
            return 0, lib.load_recipes(args.path)
        if c == "recipe":
            recipe = lib.get_recipe(args.type)
            return (0, recipe) if recipe else (1, {"recipe_type": args.type, "outcome": "NONE"})
        if c == "resolve-packet":
            return 0, lib.resolve_packet_detail(args.type)
        if c == "scan":
            report = lib.scan_shelf(record=not args.dry_run)
            return 0, {"scan_id": report.scan_id, "memory_root": report.memory_root, "files_seen": report.files_seen,
                       "folders_seen": report.folders_seen, "catalogued": report.catalogued,
                       "counts": report.counts(), "findings": report.findings}
        return 2, {"error": f"unknown command {c}"}
    except (CatalogRefusal, NotFound) as exc:
        return 1, {"refused": str(exc), "kind": type(exc).__name__}
    finally:
        lib.close()


def main(argv=None) -> int:
    code, payload = run(sys.argv[1:] if argv is None else argv)
    print(json.dumps(_jsonable(payload), indent=2, default=str))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
