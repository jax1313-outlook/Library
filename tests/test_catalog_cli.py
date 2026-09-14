"""`python -m dispatch_library.catalog`: every step a separate process, so every answer survived one."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def cli(tmp_path, *args, expect=0):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), DISPATCH_LIBRARY_CATALOG=str(tmp_path / "catalog.db"),
               DISPATCH_MEMORY_ROOT=str(tmp_path / "Memory"))
    done = subprocess.run([sys.executable, "-m", "dispatch_library.catalog", *map(str, args)], capture_output=True,
                          text=True, env=env, stdin=subprocess.DEVNULL, timeout=120)
    assert done.returncode == expect, done.stdout + done.stderr
    return json.loads(done.stdout)


def test_library_remembers_across_separate_processes(tmp_path):
    (tmp_path / "Memory" / "Templates").mkdir(parents=True)
    (tmp_path / "Memory" / "Templates" / "closeout.md").write_text("Closeout {load_id}", encoding="utf-8")

    status = cli(tmp_path, "init")
    assert (status["schema_version"], status["journal_mode"]) == (3, "wal")

    refused = cli(tmp_path, "place", "--code", "TPL-1", "--collection", "Templates", "--title", "t",
                  "--accepted-by", "Certification Operator", "--body", "b", expect=1)
    assert refused["kind"] == "MissingObjectType"

    placed = cli(tmp_path, "place", "--code", "LIB-TEMPLATES-FORM-CLOSEOUT", "--collection", "Templates",
                 "--title", "Closeout", "--type", "FORM_TEMPLATE", "--accepted-by", "Mike Zachary",
                 "--capture-channel", "JOE", "--path", "Templates/closeout.md")
    assert (placed["accepted_by"], placed["capture_channel"]) == ("Mike Zachary", "JOE")

    current = cli(tmp_path, "current", "LIB-TEMPLATES-FORM-CLOSEOUT", "--external")
    assert (current["version"], current["lifecycle_state"]) == (1, "CURRENT")

    joe = cli(tmp_path, "place", "--code", "TPL-2", "--collection", "Templates", "--title", "t", "--type",
              "FORM_TEMPLATE", "--accepted-by", "Joe", "--body", "b", expect=1)
    assert "system identity" in joe["refused"]

    candidate_file = tmp_path / "candidate.json"
    candidate_file.write_text(json.dumps({
        "submitted_by": "PUBLISHER", "source_type": "reusable packet part", "collection": "Publisher_Parts",
        "proposed_object_code": "PART-BROKER-COVER", "proposed_title": "Broker packet cover",
        "proposed_body_or_reference": "Cover page text"}), encoding="utf-8")
    unsourced = cli(tmp_path, "submit", "--json", candidate_file)["candidate_id"]
    cli(tmp_path, "confirm-type", unsourced, "PACKET_COMPONENT", "--by", "Publisher")
    failed = cli(tmp_path, "validate", unsourced, expect=1)
    assert failed["problems"] == ["no source is recorded (source trace check)"]

    data = json.loads(candidate_file.read_text(encoding="utf-8"))
    data.update(proposed_object_code="PART-BROKER-COVER-2", source_refs=[["WORKSPACE", "publisher-ws-0001"]])
    candidate_file.write_text(json.dumps(data), encoding="utf-8")
    submitted = cli(tmp_path, "submit", "--json", candidate_file)
    cid = submitted["candidate_id"]
    assert submitted["status"] == "PENDING_REVIEW"

    pending = [c["candidate_id"] for c in cli(tmp_path, "candidates", "--status", "PENDING_REVIEW")]
    assert pending == [unsourced, cid]
    assert cli(tmp_path, "validate", cid, expect=1)["passed"] is False
    cli(tmp_path, "classify", cid, "PACKET_COMPONENT")
    cli(tmp_path, "confirm-type", cid, "PACKET_COMPONENT", "--by", "Publisher")
    assert cli(tmp_path, "validate", cid)["passed"] is True
    decided = cli(tmp_path, "decide", cid, "approve", "--by", "Mike Zachary", "--capture-channel", "JOE")
    assert decided["status"] == "APPROVED"
    part = cli(tmp_path, "current", "PART-BROKER-COVER-2")
    assert (part["source"], part["object_type"], part["accepted_by"]) == ("APPROVED_CANDIDATE", "PACKET_COMPONENT", "Mike Zachary")

    (tmp_path / "Memory" / "Templates" / "closeout.md").write_text("edited", encoding="utf-8")
    scan = cli(tmp_path, "scan")
    assert scan["counts"]["CHANGED"] == 1

    final = cli(tmp_path, "status")
    assert final["counts"]["library_object"] == 2
    assert final["counts"]["library_candidate"] == 2
