from dispatch_library.models import LibraryObject, LibraryObjectSource, LibraryObjectStatus
from dispatch_library.registry import ObjectRegistry
from dispatch_library.resolver import current, list_current


def _obj(object_code, version, status, **overrides):
    kwargs = dict(
        object_code=object_code,
        collection="Reference",
        title=f"Title v{version}",
        version=version,
        status=status,
        source=LibraryObjectSource.HUMAN_PLACED,
        body_or_uri="body",
        accepted_by="Mike Zachary",
    )
    kwargs.update(overrides)
    return LibraryObject(**kwargs)


def test_current_retrieval_returns_only_current_version():
    registry = ObjectRegistry()
    registry.add_version(_obj("DOC-1", 1, LibraryObjectStatus.CURRENT))

    obj = current(registry, "DOC-1")
    assert obj is not None
    assert obj.version == 1
    assert obj.status == LibraryObjectStatus.CURRENT


def test_adding_new_current_version_supersedes_old_one():
    registry = ObjectRegistry()
    v1 = registry.add_version(_obj("DOC-1", 1, LibraryObjectStatus.CURRENT))
    v2 = registry.add_version(_obj("DOC-1", 2, LibraryObjectStatus.CURRENT, supersedes_version=1))

    assert v1.status == LibraryObjectStatus.SUPERSEDED
    assert v2.status == LibraryObjectStatus.CURRENT

    resolved = current(registry, "DOC-1")
    assert resolved.version == 2


def test_superseded_versions_never_returned_by_resolver():
    registry = ObjectRegistry()
    registry.add_version(_obj("DOC-1", 1, LibraryObjectStatus.CURRENT))
    registry.add_version(_obj("DOC-1", 2, LibraryObjectStatus.CURRENT, supersedes_version=1))
    registry.add_version(_obj("DOC-1", 3, LibraryObjectStatus.CURRENT, supersedes_version=2))

    history = registry.history("DOC-1")
    current_versions = [o for o in history if o.status == LibraryObjectStatus.CURRENT]
    assert len(current_versions) == 1
    assert current_versions[0].version == 3


def test_unknown_object_code_resolves_to_none():
    registry = ObjectRegistry()
    assert current(registry, "DOES-NOT-EXIST") is None


def test_list_current_filters_by_collection():
    registry = ObjectRegistry()
    registry.add_version(_obj("DOC-1", 1, LibraryObjectStatus.CURRENT, collection="Reference"))
    registry.add_version(_obj("DOC-2", 1, LibraryObjectStatus.CURRENT, collection="Templates"))

    ref_only = list_current(registry, collection="Reference")
    assert len(ref_only) == 1
    assert ref_only[0].object_code == "DOC-1"
