"""Two connections, two processes, one catalog file in WAL mode.

A single-connection suite cannot show any of this. These tests hold real locks across real
connections and run real operating-system processes against the same file.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from dispatch_library.catalog import CatalogBusyError, open_library

WORKER = Path(__file__).resolve().parent / "_catalog_worker.py"
PERSON = "Certification Operator"


def _place(lib, code="DOC-1", body="b"):
    return lib.ingest_human_document(code, "Reference", "t", body, PERSON, object_type="CONTROLLED_COMPANY_FACT")


def test_a_reader_sees_the_last_commit_while_a_writer_holds_the_lock(tmp_path):
    path = tmp_path / "catalog.db"
    writer = open_library(path)
    reader = open_library(path)
    _place(writer, body="committed")

    writer.connection.execute("BEGIN IMMEDIATE")
    writer.connection.execute("UPDATE library_object SET title = 'uncommitted' WHERE object_code = 'DOC-1'")
    started = time.monotonic()
    row = reader.connection.execute("SELECT title FROM library_object WHERE object_code = 'DOC-1'").fetchone()
    assert row["title"] == "t", "a WAL reader must see the last committed state"
    assert time.monotonic() - started < 1.0, "a WAL reader must not wait for a writer"
    writer.connection.execute("ROLLBACK")
    writer.close()
    reader.close()


def test_a_second_writer_past_its_busy_timeout_gets_a_clear_error(tmp_path):
    from dispatch_library.catalog import Catalog, CatalogLibraryService, open_catalog

    path = tmp_path / "catalog.db"
    holder = open_library(path)
    impatient = CatalogLibraryService(Catalog(open_catalog(path, timeout=0.3)))
    holder.connection.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(CatalogBusyError):
            _place(impatient)
    finally:
        holder.connection.execute("ROLLBACK")
    assert _place(impatient).version == 1, "once the lock is released the write goes through"
    holder.close()
    impatient.close()


def test_a_second_writer_within_its_busy_timeout_waits_and_succeeds(tmp_path):
    path = tmp_path / "catalog.db"
    holder = open_library(path)
    waiter = open_library(path)
    _place(holder)
    holder.connection.execute("BEGIN IMMEDIATE")
    release = threading.Timer(1.0, lambda: holder.connection.execute("COMMIT"))
    release.start()
    started = time.monotonic()
    obj = _place(waiter, body="after the wait")
    waited = time.monotonic() - started
    release.join()
    assert obj.version == 2
    assert waited >= 0.8, f"the second writer did not wait for the lock ({waited:.2f}s)"
    holder.close()
    waiter.close()


def _run(*args, timeout=180):
    # stdin=DEVNULL: a parent started without a console stdin (a service, a scheduled task, a
    # detached shell) otherwise fails in CreateProcess with WinError 6 before the child runs.
    return subprocess.Popen([sys.executable, str(WORKER), *map(str, args)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_two_processes_superseding_one_object_never_leave_two_current(tmp_path):
    path = tmp_path / "catalog.db"
    seed = open_library(path)
    _place(seed, code="DOC-RACE", body="seed")
    seed.close()
    procs = [_run("place", path, "DOC-RACE", 25, label) for label in ("A", "B")]
    watcher = _run("watch", path, "DOC-RACE", 6)
    outputs = []
    for proc in procs + [watcher]:
        out, err = proc.communicate(timeout=300)
        assert proc.returncode == 0, err
        outputs.append(json.loads(out))

    lib = open_library(path)
    history = lib.history("DOC-RACE")
    assert sorted(o.version for o in history) == list(range(1, 52)), "every write landed, each as its own version"
    assert [o.status.value for o in history].count("CURRENT") == 1
    chain = lib.catalog.version_rows("DOC-RACE")
    by_id = {r["version_id"]: r for r in chain}
    for row in chain[1:]:
        assert by_id[row["supersedes_version_id"]]["version_major"] == row["version_major"] - 1
    assert outputs[2]["counts"] == [1], f"a concurrent reader saw {outputs[2]['counts']} current rows"
    assert outputs[2]["samples"] > 100
    queued = lib.catalog.retention_queue()
    assert len(queued) == 51 - 1 - 3
    lib.close()


def test_two_processes_submitting_candidates_lose_nothing(tmp_path):
    path = tmp_path / "catalog.db"
    open_library(path).close()
    procs = [_run("submit", path, 20, label) for label in ("I1", "I2")]
    submitted = []
    for proc in procs:
        out, err = proc.communicate(timeout=300)
        assert proc.returncode == 0, err
        submitted += json.loads(out)["candidates"]
    lib = open_library(path)
    assert sorted(c.candidate_id for c in lib.pending_candidates()) == sorted(submitted)
    assert len(submitted) == 40
    lib.close()
