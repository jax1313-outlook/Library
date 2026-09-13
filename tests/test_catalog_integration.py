"""The catalog against the real Publisher and Intelligence packages, across process restarts.

Both repositories are separate. These tests import them only when their source is on this
machine, named by PUBLISHER_SRC and INTELLIGENCE_SRC, and skip otherwise -- they never vendor
either package into this one.
"""
from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dispatch_library.catalog import open_library
from dispatch_library.catalog.intake import DurableCandidateSink
from dispatch_library.service import LibraryService
from test_recipes import SAMPLE

PUBLISHER_SRC = os.environ.get("PUBLISHER_SRC", "")
INTELLIGENCE_SRC = os.environ.get("INTELLIGENCE_SRC", "")
PERSON = "Certification Operator"
ROOT = Path(__file__).resolve().parent.parent

needs_publisher = pytest.mark.skipif(not (PUBLISHER_SRC and Path(PUBLISHER_SRC, "dispatch_publisher").is_dir()),
                                     reason="PUBLISHER_SRC not set to the Publisher repository's src")
needs_intelligence = pytest.mark.skipif(not (INTELLIGENCE_SRC and Path(INTELLIGENCE_SRC, "dispatch_intel").is_dir()),
                                        reason="INTELLIGENCE_SRC not set to the Intelligence repository's src")


def _import_from(src, module):
    if src not in sys.path:
        sys.path.insert(0, src)
    return __import__(module, fromlist=["*"])


def _python(code: str, env_extra: dict):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "src"), *env_extra.pop("paths", [])]), **env_extra)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                          stdin=subprocess.DEVNULL, timeout=120)
    assert done.returncode == 0, done.stderr
    return done.stdout


@needs_publisher
class TestPublisherLibraryClient:
    def test_both_services_satisfy_the_protocol_signatures(self):
        client = _import_from(PUBLISHER_SRC, "dispatch_publisher.library_client")
        from dispatch_library.catalog import CatalogLibraryService

        for name, member in inspect.getmembers(client.LibraryClient, inspect.isfunction):
            if name.startswith("_"):
                continue
            wanted = list(inspect.signature(member).parameters)
            for service in (LibraryService, CatalogLibraryService):
                got = list(inspect.signature(getattr(service, name)).parameters)
                assert got[: len(wanted)] == wanted, f"{service.__name__}.{name}{got} vs protocol {wanted}"

    def test_pull_libraries_against_the_persistent_catalog_across_restarts(self, tmp_path):
        catalog = tmp_path / "catalog.db"
        recipes = tmp_path / "publisher_recipes.json"
        recipes.write_text(json.dumps(SAMPLE), encoding="utf-8")
        _python(
            "from dispatch_library.catalog import open_library\n"
            f"lib = open_library(r'{catalog}')\n"
            f"lib.load_recipes(r'{recipes}')\n"
            "for code, t in (('w9','W-9'), ('insurance_certificate','COI'), ('authority','MC authority')):\n"
            f"    lib.ingest_human_document(code, 'Company', t, t + ' on file', '{PERSON}', object_type='COMPANY_CREDENTIAL')\n"
            "lib.close()\n",
            {},
        )
        out = _python(
            "import json\n"
            "from dispatch_library.catalog import open_library\n"
            "from dispatch_publisher import service\n"
            "from dispatch_publisher.models import RecipeType\n"
            f"lib = open_library(r'{catalog}', consumer_role='PUBLISHER')\n"
            "recipe = lib.get_recipe('BROKER_ONBOARDING_PACKET')\n"
            "req = service.create_request(recipe['recipe_code'], RecipeType.BROKER_ONBOARDING_PACKET)\n"
            "ws = service.pull_libraries(req, lib)\n"
            "inv = service.create_inventory(service.create_readiness_packet(req, ws))\n"
            "notice = service.create_missing_notice(inv)\n"
            "print(json.dumps({'present': sorted(inv.present_items), 'missing': sorted(inv.missing_items),\n"
            "                  'notice': sorted(notice.missing_items) if notice else None}))\n",
            {"paths": [PUBLISHER_SRC]},
        )
        result = json.loads(out)
        assert result["present"] == ["authority", "insurance_certificate", "w9"]
        assert result["missing"] == ["company_profile"]
        assert result["notice"] == ["company_profile"]

    def test_a_review_due_credential_reaches_publisher_as_missing(self, tmp_path):
        service = _import_from(PUBLISHER_SRC, "dispatch_publisher.service")
        models = _import_from(PUBLISHER_SRC, "dispatch_publisher.models")
        recipes = tmp_path / "publisher_recipes.json"
        recipes.write_text(json.dumps(SAMPLE), encoding="utf-8")
        lib = open_library(tmp_path / "catalog.db", consumer_role="PUBLISHER")
        lib.load_recipes(recipes)
        lib.ingest_human_document("w9", "Company", "W-9", "W-9", PERSON, object_type="COMPANY_CREDENTIAL")
        req = service.create_request("R", models.RecipeType.BROKER_ONBOARDING_PACKET)
        assert "w9" in service.pull_libraries(req, lib).pulled_library_objects
        lib.set_lifecycle("w9", "REVIEW_DUE")
        assert "w9" in service.pull_libraries(req, lib).pending_parts
        lib.close()


@needs_intelligence
class TestIntelligenceRouting:
    def test_route_to_library_lands_in_the_durable_queue_and_survives_restart(self, tmp_path):
        catalog = tmp_path / "catalog.db"
        out = _python(
            "import json\n"
            "from dispatch_intel.models import IntelligenceFinding, Confidence\n"
            "from dispatch_intel.service import route_to_library\n"
            "from dispatch_library.catalog import open_library\n"
            "from dispatch_library.catalog.intake import DurableCandidateSink\n"
            "finding = IntelligenceFinding(source_type='Load board opportunity', source_reference='examples/load.txt',\n"
            "    source_excerpt='Dedicated Route - Jacksonville to Savannah Port', classification='Load board opportunity',\n"
            "    summary='Recurring lane worth keeping', confidence=Confidence.MEDIUM, routing_queue=['LIBRARY_CANDIDATE'])\n"
            f"lib = open_library(r'{catalog}')\n"
            "candidate = route_to_library(finding, store=DurableCandidateSink(lib))\n"
            "print(json.dumps({'candidate_id': candidate.candidate_id, 'finding_id': finding.finding_id,\n"
            "                  'type': type(candidate).__module__}))\n"
            "lib.close()\n",
            {"paths": [INTELLIGENCE_SRC]},
        )
        routed = json.loads(out)
        assert routed["type"] == "dispatch_intel.models", "the candidate was built by the real Intelligence package"

        lib = open_library(catalog)
        pending = lib.pending_candidates()
        assert [c.candidate_id for c in pending] == [routed["candidate_id"]]
        assert pending[0].source_finding_id == routed["finding_id"]
        lib.classify_candidate(routed["candidate_id"], "VALIDATED_INTELLIGENCE_SUMMARY")
        lib.confirm_object_type(routed["candidate_id"], "VALIDATED_INTELLIGENCE_SUMMARY", "Intelligence")
        assert lib.validate_candidate(routed["candidate_id"])["passed"]
        lib.close()

        final = _python(
            "from dispatch_library.catalog import open_library\n"
            f"lib = open_library(r'{catalog}')\n"
            f"c = lib.review_candidate('{routed['candidate_id']}', True, '{PERSON}')\n"
            f"print(c.status.value, lib.current('CAND-{routed['finding_id'][:8]}').source.value)\n",
            {},
        )
        assert final.split() == ["APPROVED", "APPROVED_CANDIDATE"]

    def test_the_contract_fields_are_identical(self):
        intel = _import_from(INTELLIGENCE_SRC, "dispatch_intel.models")
        import dataclasses

        from dispatch_library.models import INTELLIGENCE_CANDIDATE_FIELDS, LibraryCandidate

        theirs = [(f.name, f.default if f.default is not dataclasses.MISSING else "-") for f in dataclasses.fields(intel.LibraryCandidate)]
        ours = [(f.name, f.default if f.default is not dataclasses.MISSING else "-") for f in dataclasses.fields(LibraryCandidate)]
        assert [n for n, _ in theirs] == list(INTELLIGENCE_CANDIDATE_FIELDS)
        assert [(n, getattr(d, "value", d)) for n, d in ours[:12]] == [(n, getattr(d, "value", d)) for n, d in theirs]
        assert {m.value for m in intel.SubmittedBy} <= {"INTELLIGENCE", "PUBLISHER", "HUMAN", "DISPATCH"}
        assert set(intel.LIBRARY_COLLECTIONS) == set(__import__("dispatch_library.taxonomy", fromlist=["x"]).COLLECTIONS)


def test_sink_records_only_what_it_received(tmp_path):
    from dispatch_library.models import LibraryCandidate, SubmittedBy

    lib = open_library(tmp_path / "catalog.db")
    sink = DurableCandidateSink(lib)
    sink.save_library_candidate(LibraryCandidate(submitted_by=SubmittedBy.INTELLIGENCE, source_type="s",
                                                 collection="Reference", proposed_object_code="CAND-1",
                                                 proposed_title="t", proposed_body_or_reference="b",
                                                 source_finding_id="f-1"))
    assert [c.proposed_object_code for c in sink.list_library_candidates()] == ["CAND-1"]
    assert lib.candidate(sink.received[0]).status.value == "PENDING_REVIEW"
    lib.close()
