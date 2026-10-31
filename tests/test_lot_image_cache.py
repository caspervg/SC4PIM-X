import pytest

from sc4pimx import lot_image_cache as lic
from sc4pimx import paths
from sc4pimx.SC4CityContext import EDGE_VIEW_ROTATION, EDGE_XMIN, EDGE_ZMAX

# Verified test lots from the downstream whitelist (GID:IID).
AIG_TOWER = (0xA8FBD372, 0xC6BB6905)
SILBERTURM = (0xA8FBD372, 0x160A0EDC)


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "user_data_dir", lambda: tmp_path)
    return tmp_path


def test_a_lot_has_eight_distinct_views():
    views = lic.lot_views()
    assert len(views) == 8
    assert len(set(views)) == 8
    # Four sides, each in day and night.
    assert {v.side for v in views} == {"S", "W", "N", "E"}
    assert {v.night for v in views} == {False, True}


def test_view_side_letter_follows_rep3_orientation():
    assert [lic.LotView(r, False).side for r in range(4)] == ["S", "W", "N", "E"]


def test_view_path_matches_the_filename_convention(user_dir):
    gid, iid = AIG_TOWER
    path = lic.lot_view_path(gid, iid, lic.LotView(0, night=False))
    assert path.name == "0xa8fbd372-0xc6bb6905-S-D.png"
    assert path == paths.image_db_lots_path(gid, iid, "S", night=False)


def test_default_view_faces_the_first_required_road_side():
    # Front road only (bit 3) -> South, unrotated.
    assert lic.default_lot_view(0b1000) == lic.LotView(EDGE_VIEW_ROTATION[EDGE_ZMAX], False)
    # Left road only (bit 0) -> West.
    assert lic.default_lot_view(0b0001) == lic.LotView(EDGE_VIEW_ROTATION[EDGE_XMIN], False)
    # Night flag is carried through.
    assert lic.default_lot_view(0b1000, night=True).night is True


def test_default_view_degrades_to_south_for_missing_flags():
    assert lic.default_lot_view(None) == lic.LotView(0, False)
    assert lic.default_lot_view("nonsense").side == "S"


def _write_all_views(gid, iid):
    lic.image_db_lots_dir().mkdir(parents=True, exist_ok=True)
    for view in lic.lot_views():
        lic.lot_view_path(gid, iid, view).write_bytes(b"PNG")


def test_cache_version_roundtrip_and_current(user_dir):
    assert lic.read_cache_version() is None
    assert lic.cache_valid_since() is None
    lic.write_cache_version(valid_since=1000.5)
    assert lic.read_cache_version() == lic.LOT_PREVIEW_GENERATOR_VERSION
    # Backed off to absorb coarse filesystem mtimes.
    assert lic.cache_valid_since() == 1000 - lic._MTIME_SLACK
    # A stale (older) version is not current.
    lic.write_cache_version(lic.LOT_PREVIEW_GENERATOR_VERSION - 1)
    assert lic.cache_valid_since() is None


def test_cache_version_without_valid_since_is_not_current(user_dir):
    lic.image_db_lots_dir().mkdir(parents=True, exist_ok=True)
    lic.cache_version_path().write_text(str(lic.LOT_PREVIEW_GENERATOR_VERSION), encoding="utf-8")
    assert lic.cache_valid_since() is None


def test_ensure_cache_version_keeps_a_current_stamp(user_dir):
    lic.write_cache_version(valid_since=1000)
    assert lic.ensure_cache_version(5000) == 1000 - lic._MTIME_SLACK


def test_ensure_cache_version_restamps_an_older_version(user_dir):
    lic.write_cache_version(lic.LOT_PREVIEW_GENERATOR_VERSION - 1, valid_since=1000)
    assert lic.ensure_cache_version(5000) == 5000 - lic._MTIME_SLACK
    assert lic.read_cache_version() == lic.LOT_PREVIEW_GENERATOR_VERSION


def test_images_written_after_stamping_count_as_current(user_dir):
    # A run stamps before rendering, so whatever it wrote before a cancel is
    # already current and the next run resumes instead of starting over.
    gid, iid = AIG_TOWER
    valid_since = lic.ensure_cache_version()
    _write_all_views(gid, iid)
    assert lic.stale_lot_pictures([(gid, iid, None)], valid_since) == []
    assert lic.stale_lot_pictures([(gid, iid, None)], lic.cache_valid_since()) == []


def test_lot_view_fresh_considers_presence_version_and_mtime(user_dir):
    gid, iid = AIG_TOWER
    view = lic.LotView(0, night=False)
    assert lic.lot_view_fresh(gid, iid, view) is False  # missing
    _write_all_views(gid, iid)
    assert lic.lot_view_fresh(gid, iid, view) is True
    mtime = lic.lot_view_path(gid, iid, view).stat().st_mtime
    # No current-generation stamp makes it stale.
    assert lic.lot_view_fresh(gid, iid, view, valid_since=None) is False
    # Written before the current generator took effect -> stale.
    assert lic.lot_view_fresh(gid, iid, view, valid_since=mtime + 1000) is False
    assert lic.lot_view_fresh(gid, iid, view, valid_since=mtime - 1000) is True
    # A lot modified after the render (future mtime) makes it stale.
    assert lic.lot_view_fresh(gid, iid, view, updated=mtime + 1000) is False
    assert lic.lot_view_fresh(gid, iid, view, updated=mtime - 1000) is True


def test_stale_lot_pictures_flags_missing_version_and_modified(user_dir):
    gid, iid = AIG_TOWER
    _write_all_views(gid, iid)
    mtime = lic.lot_view_path(gid, iid, lic.LotView(0, False)).stat().st_mtime
    # Fresh cache, current version, lot older than files -> nothing to render.
    assert lic.stale_lot_pictures([(gid, iid, mtime - 10)], valid_since=mtime - 10) == []
    # Lot modified after render -> all eight views stale.
    worklist = lic.stale_lot_pictures([(gid, iid, mtime + 10)], valid_since=mtime - 10)
    assert len(worklist) == 8
    # Old generator version -> all eight stale regardless of mtime.
    assert len(lic.stale_lot_pictures([(gid, iid, None)], valid_since=None)) == 8
    # Rendered before the current version took effect -> all eight stale.
    assert len(lic.stale_lot_pictures([(gid, iid, None)], valid_since=mtime + 10)) == 8
    # Missing lot -> all eight stale.
    assert len(lic.stale_lot_pictures([SILBERTURM + (None,)], valid_since=mtime - 10)) == 8
