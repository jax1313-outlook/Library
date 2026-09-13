"""Reading the shelf, and noticing when it and the catalog disagree.

The shelf is a directory of real files that people open, edit and move --
`DISPATCH_MEMORY_ROOT`, which on Mike's machine is `D:\\Memory`. The catalog
records what stands for what. The two drift, because the shelf is used by
humans and the catalog is written by a program, and drift that nobody notices
is how a Publisher packet ends up built from a document that changed last
month.

`scan()` walks the shelf and reports three things:

    UNCATALOGUED  a file is there and no object stands for it
    CHANGED       an object stands for it and the bytes are not what was recorded
    MISSING       an object stands for a file that is not on the shelf

**The scan never writes to the shelf.** It opens files to hash them and that is
all -- no mkdir, no touch, no repair. Retrieval is not modification.

**The scan never adopts a file.** An UNCATALOGUED file is reported, never
turned into a Library object. Placing a document is an acceptance and an
acceptance needs a human's name on it; a program that catalogued files it found
would be manufacturing approvals by walking a directory.

**A MISSING file is a defect, not a deletion.** The catalog row stays. Library
does not quietly forget an object because a file moved.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

UNCATALOGUED = "UNCATALOGUED"
CHANGED = "CHANGED"
MISSING = "MISSING"

#: Never reported as uncatalogued. These are not documents -- they are the
#: operating system's and the version control system's litter, and a scan that
#: reported them would bury the findings that matter.
IGNORED_NAMES = frozenset({
    ".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep", ".gitignore",
})
IGNORED_DIRECTORIES = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".svn", "$RECYCLE.BIN",
    "System Volume Information",
})
IGNORED_SUFFIXES = frozenset({".tmp", ".swp", ".pyc", ".lock"})

_READ_CHUNK = 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_of(path: Path) -> str:
    """The file's digest, read in chunks so a large document does not have to
    fit in memory all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_READ_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def is_ignorable(path: Path) -> bool:
    if path.name in IGNORED_NAMES or path.suffix.lower() in IGNORED_SUFFIXES:
        return True
    return any(part in IGNORED_DIRECTORIES for part in path.parts)


@dataclass(frozen=True)
class Finding:
    """One disagreement between the shelf and the catalog."""

    relative_path: str
    finding: str
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"[{self.finding}] {self.relative_path} {self.detail}".rstrip()


@dataclass
class ScanResult:
    scan_id: Optional[int]
    memory_root: str
    files_seen: int = 0
    catalogued: int = 0
    findings: List[Finding] = field(default_factory=list)

    def of(self, kind: str) -> List[Finding]:
        return [f for f in self.findings if f.finding == kind]

    @property
    def uncatalogued(self) -> List[Finding]:
        return self.of(UNCATALOGUED)

    @property
    def changed(self) -> List[Finding]:
        return self.of(CHANGED)

    @property
    def missing(self) -> List[Finding]:
        return self.of(MISSING)

    @property
    def clean(self) -> bool:
        return not self.findings


def walk_shelf(root: Path) -> Iterable[Path]:
    """Every file on the shelf worth looking at, in a stable order.

    Sorted so two scans of an unchanged shelf produce findings in the same
    order -- a report whose lines move around between runs is a report nobody
    can diff.
    """
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.rglob("*") if p.is_file() and not is_ignorable(p.relative_to(root))),
        key=lambda p: p.as_posix(),
    )


def scan(
    connection: sqlite3.Connection,
    memory_root: Path | str,
    *,
    record: bool = True,
) -> ScanResult:
    """Compare the shelf against the catalog.

    `record=False` is the dry run: it reads the shelf and the catalog and
    returns exactly the same findings, writing nothing at all. Run it first.
    """
    root = Path(memory_root)
    started = _now()

    catalogued: Dict[str, sqlite3.Row] = {
        row["relative_path"]: row
        for row in connection.execute(
            "SELECT object_code, version, relative_path, content_sha256, size_bytes "
            "FROM library_object WHERE status = 'CURRENT' AND relative_path IS NOT NULL"
        )
    }

    result = ScanResult(scan_id=None, memory_root=str(root))
    seen: set[str] = set()

    for path in walk_shelf(root):
        relative = path.relative_to(root).as_posix()
        seen.add(relative)
        result.files_seen += 1

        row = catalogued.get(relative)
        if row is None:
            result.findings.append(Finding(
                relative, UNCATALOGUED,
                "on the shelf, no Library object stands for it",
            ))
            continue

        result.catalogued += 1
        digest = sha256_of(path)
        if row["content_sha256"] and digest != row["content_sha256"]:
            result.findings.append(Finding(
                relative, CHANGED,
                f"{row['object_code']} v{row['version']} recorded "
                f"{row['content_sha256'][:12]}, file is {digest[:12]}",
            ))

    for relative, row in sorted(catalogued.items()):
        if relative not in seen:
            result.findings.append(Finding(
                relative, MISSING,
                f"{row['object_code']} v{row['version']} stands for a file that is not there",
            ))

    if record:
        result.scan_id = _record(connection, result, started)
    return result


def _record(connection: sqlite3.Connection, result: ScanResult, started: str) -> int:
    """Write the scan and its findings, so drift is a record not a console line.

    Note what is written: a scan row and finding rows. No `library_object` row
    is created, updated or deleted by a scan. The scan reports; a person acts.
    """
    with connection:
        cursor = connection.execute(
            "INSERT INTO catalog_scan (started_at, finished_at, memory_root, files_seen, "
            "catalogued, uncatalogued, changed, missing) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                started, _now(), result.memory_root, result.files_seen, result.catalogued,
                len(result.uncatalogued), len(result.changed), len(result.missing),
            ),
        )
        scan_id = int(cursor.lastrowid)
        for finding in result.findings:
            connection.execute(
                "INSERT OR REPLACE INTO catalog_finding "
                "(scan_id, relative_path, finding, detail) VALUES (?, ?, ?, ?)",
                (scan_id, finding.relative_path, finding.finding, finding.detail),
            )
    return scan_id


def findings_of(connection: sqlite3.Connection, scan_id: int) -> List[Finding]:
    return [
        Finding(row["relative_path"], row["finding"], row["detail"])
        for row in connection.execute(
            "SELECT relative_path, finding, detail FROM catalog_finding "
            "WHERE scan_id = ? ORDER BY finding, relative_path",
            (scan_id,),
        )
    ]


def last_scan(connection: sqlite3.Connection) -> Optional[dict]:
    row = connection.execute(
        "SELECT * FROM catalog_scan ORDER BY scan_id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None
