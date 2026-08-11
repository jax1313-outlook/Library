from dispatch_library.taxonomy import COLLECTIONS, is_valid_collection


def test_taxonomy_has_exactly_15_collections():
    assert len(COLLECTIONS) == 15


def test_taxonomy_matches_system_relationship_matrix_section_7():
    expected = {
        "Constitution", "Process", "Operations", "Compliance", "Training", "Reference",
        "Templates", "Company", "Customer", "Broker", "Location_Intelligence",
        "Route_Intelligence", "Publisher_Parts", "Security", "Index",
    }
    assert set(COLLECTIONS) == expected


def test_is_valid_collection():
    assert is_valid_collection("Publisher_Parts") is True
    assert is_valid_collection("Not_A_Collection") is False
