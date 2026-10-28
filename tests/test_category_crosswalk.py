"""Tests for the shared source-category to GCC taxonomy resolver."""

from scripts.category_crosswalk import resolve_source_category


def test_explicit_ntee_code_maps_to_supported_target_fields() -> None:
    result = resolve_source_category("C01")

    assert result["climate_category"] == "Environmental"
    assert result["action_category"] == "Advocacy/Policy"
    assert result["activity"] == "Advocacy"
    assert result["resilience"] == "Unknown"
    assert result["mapping_basis"] == "IRS/ProPublica NTEE C01"


def test_equivalent_ntee_label_resolves_without_a_code() -> None:
    result = resolve_source_category(
        source_category="Energy Resources Conservation and Development"
    )

    assert result["ntee_code"] == "C35"
    assert result["climate_category"] == "Energy Efficiency"
    assert result["resilience"] == "Mitigation"


def test_unrecognized_source_category_remains_unknown() -> None:
    result = resolve_source_category(source_category="Novel unsupported category")

    assert result["ntee_code"] == ""
    assert result["climate_category"] == "Unknown"
    assert result["action_category"] == "Unknown"
