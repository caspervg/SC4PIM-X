from sc4pimx.DependenciesDlg import (
    DependencyRow,
    dependency_package_buckets,
    filter_catalog_matches,
    found_catalog_status,
    is_ignored_sound_iid,
    is_builtin_game_file,
    lookup_catalog,
    package_bucket_display_text,
    row_display_label,
)
from sc4pimx.DependencyCatalog import CatalogLookupResult


class FakeCatalogClient:
    def __init__(self, tgi_result, iid_result):
        self.tgi_result = tgi_result
        self.iid_result = iid_result
        self.tgi_requests = []
        self.iid_requests = []

    def search_tgi(self, tgi):
        self.tgi_requests.append(tgi)
        return self.tgi_result

    def search_iid(self, iid):
        self.iid_requests.append(iid)
        return self.iid_result


def test_found_catalog_lookup_uses_exact_tgi_only():
    client = FakeCatalogClient(
        CatalogLookupResult("ok", []),
        CatalogLookupResult("ok", [{"Package": "should-not-use"}]),
    )

    status, matches, reason = lookup_catalog(
        client,
        tgi=(0x6534284A, 0x5AD0E817, 0x12345678),
        iid=0x12345678,
        catalog_category="Model",
        allow_iid_fallback=False,
    )

    assert status == "ok"
    assert matches == []
    assert reason == ""
    assert client.tgi_requests == [(0x6534284A, 0x5AD0E817, 0x12345678)]
    assert client.iid_requests == []


def test_builtin_game_files_are_not_catalog_pending():
    assert is_builtin_game_file(r"C:\Games\SimCity 4\SimCity_1.dat")
    assert is_builtin_game_file("sound.dat")
    assert is_builtin_game_file("SimCityLocale.dat")
    assert is_builtin_game_file("EP1.dat")
    assert not is_builtin_game_file("EP.dat")
    assert is_builtin_game_file("merged.dat")
    assert is_builtin_game_file("cohorts.dat")
    assert not is_builtin_game_file("BSC MEGA Props - SG Vol01.dat")
    assert not is_builtin_game_file("simcity_6.dat")

    status = found_catalog_status(
        "simcity_3.dat",
        (0x6534284A, 0x5AD0E817, 0x12345678),
        catalog_enabled=True,
        catalog_base_url="https://catalog.example",
    )

    assert status == "built_in"


def test_missing_catalog_lookup_falls_back_to_group_filtered_iid_match():
    client = FakeCatalogClient(
        CatalogLookupResult("ok", []),
        CatalogLookupResult("ok", [
            {
                "Package": "wrong-group",
                "TGI": "0x6534284A, 0x00000000, 0x12345678",
                "Category": "Model",
            },
            {
                "Package": "right-group",
                "TGI": "0x6534284A, 0x5AD0E817, 0x12345678",
                "Category": "Model",
            },
        ]),
    )

    status, matches, reason = lookup_catalog(
        client,
        tgi=(0x6534284A, 0x5AD0E817, 0x12345678),
        iid=0x12345678,
        catalog_category="Model",
    )

    assert status == "ok"
    assert reason == "iid_fallback"
    assert [match["Package"] for match in matches] == ["right-group"]


def test_filter_catalog_matches_keeps_uncategorized_fallbacks():
    matches = [
        {"Package": "uncategorized"},
        {"Package": "texture", "Category": "Texture"},
        {"Package": "prop", "Category": "Prop"},
    ]

    filtered = filter_catalog_matches(matches, "Texture")

    assert [match["Package"] for match in filtered] == ["uncategorized", "texture"]


def test_dependency_buckets_group_missing_and_installed_catalog_packages():
    match = {
        "Package": "bsc:mega-props-sg-vol01",
        "FileName": "BSC MEGA Props - SG Vol01.dat",
        "Websites": "https://example.test/sg",
        "TGI": "0x6534284A, 0x5AD0E817, 0x12345678",
    }
    rows = [
        DependencyRow(
            id=1,
            status="found",
            kind="Prop",
            name="SG Prop",
            key="0x6534284A-0x5AD0E817-0x12345678",
            source="BSC MEGA Props - SG Vol01.dat",
            referenced_by="Props: SG Prop",
            catalog_status="checked",
            catalog_matches=[match],
            catalog_match_reason="exact_tgi",
        ),
        DependencyRow(
            id=2,
            status="missing",
            kind="Model",
            name="",
            key="0x6534284A-0x5AD0E817-0x12345678",
            source="not found",
            referenced_by="Props: SG Prop",
            catalog_status="checked",
            catalog_matches=[match],
            catalog_match_reason="iid_fallback",
        ),
    ]

    buckets = dependency_package_buckets(rows)

    bucket = buckets["bsc:mega-props-sg-vol01"]
    assert bucket["found_count"] == 1
    assert bucket["missing_count"] == 1
    assert package_bucket_display_text(bucket) == "bsc:mega-props-sg-vol01\nBSC MEGA Props - SG Vol01.dat"


def test_known_missing_maxis_sound_is_ignored():
    assert is_ignored_sound_iid(0x8A8B7DD1)
    assert is_ignored_sound_iid("0x8A8B7DD1")
    assert not is_ignored_sound_iid(0x8A8B7DD2)


def test_dependency_label_uses_typed_id_when_name_is_unknown_or_generic():
    prop_row = DependencyRow(
        id=1,
        status="missing",
        kind="Prop",
        name="",
        key="0x12345678",
        source="not found",
        referenced_by="Props",
        catalog_name="Prop",
    )
    texture_row = DependencyRow(
        id=2,
        status="missing",
        kind="Texture",
        name="Texture",
        key="0x7AB50E44",
        source="not found",
        referenced_by="Textures",
    )
    model_row = DependencyRow(
        id=3,
        status="missing",
        kind="Model",
        name="",
        key="0x6534284A-0x5AD0E817-0x89ABCDEF",
        source="not found",
        referenced_by="Props: Known Prop",
    )
    named_prop_row = DependencyRow(
        id=4,
        status="found",
        kind="Prop",
        name="Prop: Fire Occupant",
        key="0x87654321",
        source="plugin.dat",
        referenced_by="Props",
    )

    assert row_display_label(prop_row) == "Props: 0x12345678"
    assert row_display_label(texture_row) == "Textures: 0x7AB50E44"
    assert row_display_label(model_row) == "Models: 0x6534284A-0x5AD0E817-0x89ABCDEF"
    assert row_display_label(named_prop_row) == "Prop: Fire Occupant"
