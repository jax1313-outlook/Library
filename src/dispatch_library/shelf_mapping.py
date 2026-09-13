"""
The `D:\\Memory` folder -> Library collection mapping (LIBRARY_IMPLEMENTATION_PLAN_v1.md S9).

Built from the folder listing of `D:\\Memory` taken on 2026-09-13: eighteen top-level folders.
Every folder maps to at most one of the fifteen collections in `taxonomy.py`. No collection is
created here, and a folder that fits none is UNCATALOGUED rather than forced into `Reference`.

Three bases. The two-tier model and every row below were approved by Mike Zachary on 2026-09-13
(owner ruling, rulings 4 and 5):

    NAME_MATCH          the folder name is the collection name
    DOCTRINE_SUPPORTED  no name match; the Library Department Core Object Model places the
                        folder's content in one collection, cited per row, and Mike approved it
    UNMAPPED            neither; reported as it is, pending ownership review

The mapping is a lookup. Nothing here moves, renames, opens, or writes anything under the memory
root; `map_memory_root()` only lists directories and counts files.

PLACEMENT_CONFLICTS records files that sit in a folder whose collection does not fit them. Each
carries a recommended collection and nothing more: Mike decides any physical relocation
separately, and no code here acts on a recommendation.

NOT DONE: plan S9 also calls for this table to be catalogued as an `Index` object. That needs the
persistent catalog, which waits on the corrected schema's review.
"""
from __future__ import annotations

import dataclasses
import sys
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from dispatch_library.taxonomy import COLLECTIONS, require_valid_collection

COM = "Library Department Core Object Model"


class MappingBasis(str, Enum):
    NAME_MATCH = "NAME_MATCH"
    DOCTRINE_SUPPORTED = "DOCTRINE_SUPPORTED"
    UNMAPPED = "UNMAPPED"


@dataclasses.dataclass(frozen=True)
class FolderMapping:
    folder: str
    collection: Optional[str]
    basis: MappingBasis
    citation: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.basis is MappingBasis.UNMAPPED:
            if self.collection is not None:
                raise ValueError(f"{self.folder!r}: an unmapped folder has no collection")
        else:
            if self.collection is None:
                raise ValueError(f"{self.folder!r}: a mapped folder needs a collection")
            require_valid_collection(self.collection)
        if not self.citation:
            raise ValueError(f"{self.folder!r}: every row states its basis")


_N, _D, _U = MappingBasis.NAME_MATCH, MappingBasis.DOCTRINE_SUPPORTED, MappingBasis.UNMAPPED

MEMORY_FOLDER_MAPPING: Tuple[FolderMapping, ...] = (
    FolderMapping("Company Library", "Company", _N, "folder name",
                  "Every file in it on 2026-09-13 is a placement conflict; see PLACEMENT_CONFLICTS."),
    FolderMapping("Broker Library", "Broker", _N, "folder name"),
    FolderMapping("Customer Library", "Customer", _N, "folder name"),
    FolderMapping("Location Intelligence", "Location_Intelligence", _N, "folder name"),
    FolderMapping("Templates", "Templates", _N, "folder name"),
    FolderMapping("Compliance", "Compliance", _N, "folder name"),

    FolderMapping("Procedures", "Process", _D, f"{COM} §4, SOP / Workflow -> Process Library"),
    FolderMapping("Manuals", "Training", _D, f"{COM} §4, Training Asset / Manual -> Training Library"),
    FolderMapping("Forms", "Templates", _D, f"{COM} §4, Form / Template -> Templates Library"),
    FolderMapping("Insurance", "Company", _D,
                  f"{COM} §4, Company Credential (W-9, insurance, authority ...) -> Company Library"),
    FolderMapping("Equipment", "Company", _D,
                  f"{COM} §2 and §4, Capability Asset (fleet/equipment) -> Company Library",
                  "Operational Instruction carries an equipment_scope field, but that is metadata "
                  "on an Operations object, not a place for equipment records."),
    FolderMapping("Certifications", "Compliance", _D,
                  f"{COM} §4, Compliance Asset (credentials/certifications/policies) -> Compliance Library",
                  "Company Credential also names SDVOSB, so a certification may belong in Company."),

    FolderMapping("Operational Intelligence", None, _U,
                  f"{COM} §1.1 spans broker, location, route, return-route, market and pattern "
                  "intelligence, which is several collections, not one",
                  "Not Operations: that collection holds operational instructions."),
    FolderMapping("Receipts", None, _U,
                  "no collection; Dispatch describes the memory root as where receipts live "
                  "(dispatch_launcher/settings.py:133), and completed records belong to Archive"),
    FolderMapping("Fuel", None, _U, "no collection"),
    FolderMapping("Drivers", None, _U,
                  f"{COM} §2 names driver qualifications as Company assets, but a Drivers folder is "
                  "not limited to qualifications"),
    FolderMapping("Evidence", None, _U,
                  f"{COM} §1.1 gives evidence to Archive; Dispatch writes uploads to "
                  "MemoryRoot/Evidence (bootstrap_d_drive.py:182)"),
    FolderMapping("Documents", None, _U, "no collection; the name says nothing about content"),
)

@dataclasses.dataclass(frozen=True)
class PlacementConflict:
    relative_path: str  # under the memory root, POSIX separators
    kind: str
    recommended_collection: Optional[str]  # None means Archive referral, not a collection
    note: str = ""

    def __post_init__(self) -> None:
        if self.recommended_collection is not None:
            require_valid_collection(self.recommended_collection)


_AWC = "Company Library/Agent Worker Constitutions"
_WORKER = "worker constitution"
_RESEARCH = "research or reference paper"
_IF_CURRENT = "Constitution if current; Archive referral if historical or superseded."

# Observed by the read-only scan of 2026-09-13. Recommendations only (owner ruling 5).
PLACEMENT_CONFLICTS: Tuple[PlacementConflict, ...] = tuple(
    [PlacementConflict(f"{_AWC}/{name}", _WORKER, "Constitution", _IF_CURRENT) for name in (
        "00_DISPATCH_WORKER_CONSTITUTION_ARCHITECTURE.md",
        "01_DISPATCH_MASTER_WORKER_CONSTITUTION.md",
        "02_JOE_WORKER_CONSTITUTION.md",
        "03_INTELLIGENCE_WORKER_CONSTITUTION.md",
        "04_PUBLISHER_WORKER_CONSTITUTION.md",
        "05_LIBRARY_WORKER_CONSTITUTION.md",
        "06_ARCHIVE_WORKER_CONSTITUTION.md",
        "07_DISPATCH_WORKER_CONSTITUTION.md",
        "08_WORKER_RELATIONSHIPS_AND_HANDOFFS.md",
        "09_SUBCONTRACTOR_BUILD_RULES.md",
        "README.md",
    )]
    + [
        PlacementConflict(f"{_AWC}/DISPATCH_WORKER_CONSTITUTION_PACKAGE_v1.zip", _WORKER,
                          "Constitution",
                          "Holds byte-identical copies of the eleven files beside it (SHA-256 "
                          "compared 2026-09-13). A second copy, not separate content."),
        PlacementConflict("Company Library/Operational Memory Systems in Organizations 1.docx",
                          _RESEARCH, "Reference", "The trailing ' 1' suggests a copy."),
        PlacementConflict("Company Library/Freight Visibility for Regional Carriers 2.docx",
                          _RESEARCH, "Reference", "The trailing ' 2' suggests a copy."),
        PlacementConflict(
            "Company Library/Freight System Design Package – Cargo Van + Trailer Operation.docx",
            _RESEARCH, "Reference"),
        PlacementConflict("Company Library/Library Department Core Object Model 1.docx",
                          _RESEARCH, "Reference",
                          "Same text as D:\\Library\\Library Department Core Object Model.docx "
                          "(different bytes: embedded media). Which copy is canonical is Mike's call."),
    ]
)

_BY_FOLDER = {m.folder.casefold(): m for m in MEMORY_FOLDER_MAPPING}
if len(_BY_FOLDER) != len(MEMORY_FOLDER_MAPPING):
    raise RuntimeError("MEMORY_FOLDER_MAPPING names a folder twice")


def mapping_for(folder: str) -> Optional[FolderMapping]:
    """The row for a top-level folder name, matched case-insensitively as Windows does."""
    return _BY_FOLDER.get(folder.casefold())


def collections_without_a_folder() -> List[str]:
    mapped = {m.collection for m in MEMORY_FOLDER_MAPPING if m.collection}
    return [c for c in COLLECTIONS if c not in mapped]


@dataclasses.dataclass(frozen=True)
class ObservedFolder:
    folder: str
    file_count: int
    mapping: FolderMapping


@dataclasses.dataclass(frozen=True)
class MappingReport:
    memory_root: str
    folders: Tuple[ObservedFolder, ...]
    root_files: Tuple[str, ...]
    table_rows_not_on_disk: Tuple[str, ...]


def map_memory_root(root: Path) -> MappingReport:
    """Report every top-level folder under `root` against the table. Read-only.

    A folder on disk that the table does not name is reported UNMAPPED. Loose files at the
    root are listed, since they sit in no folder and therefore in no collection.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"memory root {root} is not a directory")

    folders = []
    root_files = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if entry.is_dir():
            row = mapping_for(entry.name) or FolderMapping(
                entry.name, None, _U, "folder is not in MEMORY_FOLDER_MAPPING; needs an owner decision"
            )
            count = sum(1 for p in entry.rglob("*") if p.is_file())
            folders.append(ObservedFolder(entry.name, count, row))
        elif entry.is_file():
            root_files.append(entry.name)

    on_disk = {f.folder.casefold() for f in folders}
    absent = tuple(m.folder for m in MEMORY_FOLDER_MAPPING if m.folder.casefold() not in on_disk)
    return MappingReport(str(root), tuple(folders), tuple(root_files), absent)


def format_report(report: MappingReport) -> str:
    lines = [f"Memory root: {report.memory_root}", ""]
    for basis in MappingBasis:
        rows = [f for f in report.folders if f.mapping.basis is basis]
        lines.append(f"{basis.value} ({len(rows)})")
        for f in rows:
            target = f.mapping.collection or "-"
            lines.append(f"  {f.folder:<26} -> {target:<22} files={f.file_count:<5} {f.mapping.citation}")
        lines.append("")
    lines.append("Collections with no folder: " + (", ".join(collections_without_a_folder()) or "none"))
    if report.root_files:
        lines.append("Loose files at the root (no collection): " + ", ".join(report.root_files))
    if report.table_rows_not_on_disk:
        lines.append("In the table but not on disk: " + ", ".join(report.table_rows_not_on_disk))

    root = Path(report.memory_root)
    lines += ["", f"Placement conflicts ({len(PLACEMENT_CONFLICTS)}) — recommendations only, nothing is moved"]
    for c in PLACEMENT_CONFLICTS:
        present = "present" if (root / c.relative_path).is_file() else "NOT FOUND"
        target = c.recommended_collection or "Archive referral"
        lines.append(f"  [{present}] {c.relative_path} -> {target}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(r"D:\Memory")
    print(format_report(map_memory_root(root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
