"""A separate process that writes to a catalog. Used by the concurrency and restart tests.

    python _catalog_worker.py place CATALOG CODE COUNT LABEL
    python _catalog_worker.py submit CATALOG COUNT LABEL
    python _catalog_worker.py watch CATALOG CODE SECONDS
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dispatch_library.catalog import open_library  # noqa: E402


def main(argv):
    command, catalog = argv[0], argv[1]
    lib = open_library(catalog)
    try:
        if command == "place":
            code, count, label = argv[2], int(argv[3]), argv[4]
            done = []
            for i in range(count):
                obj = lib.ingest_human_document(code, "Reference", f"{label}-{i}", f"{label} body {i}",
                                                "Certification Operator", object_type="CONTROLLED_COMPANY_FACT")
                done.append(obj.version)
            print(json.dumps({"label": label, "versions": done}))
        elif command == "submit":
            count, label = int(argv[2]), argv[3]
            ids = []
            for i in range(count):
                row = lib.catalog.submit_candidate(
                    submitted_by_role="INTELLIGENCE", source_type="finding", collection="Reference",
                    proposed_object_code=f"CAND-{label}-{i}", proposed_title="t", proposed_body_or_reference="b",
                    source_finding_id=f"finding-{label}-{i}")
                ids.append(row["candidate_id"])
            print(json.dumps({"label": label, "candidates": ids}))
        elif command == "watch":
            code, seconds = argv[2], float(argv[3])
            end = time.monotonic() + seconds
            samples = []
            while time.monotonic() < end:
                n = lib.connection.execute(
                    "SELECT count(*) FROM library_current WHERE object_code = ?", (code,)).fetchone()[0]
                samples.append(n)
            print(json.dumps({"samples": len(samples), "counts": sorted(set(samples))}))
    finally:
        lib.close()


if __name__ == "__main__":
    main(sys.argv[1:])
