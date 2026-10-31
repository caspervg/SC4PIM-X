from pathlib import Path

import pytest

from sc4pimx import paths
from sc4pimx.SC4CityContext import (
    EDGE_VIEW_ROTATION,
    EDGE_XMAX,
    EDGE_XMIN,
    EDGE_ZMAX,
    EDGE_ZMIN,
    LOT_VIEW_SIDES,
    ROAD_FLAG_EDGES,
    required_road_default_rotation,
    road_edges_from_flags,
)

# Verified test lots from the downstream whitelist (GID:IID).
AIG_TOWER = (0xA8FBD372, 0xC6BB6905)


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "user_data_dir", lambda: tmp_path)
    return tmp_path


def test_lots_cache_is_a_sibling_of_the_model_image_db(user_dir):
    lots = paths.image_db_lots_dir()
    assert lots == user_dir / "ImageDBLots"
    assert lots.parent == paths.image_db_dir().parent


def test_lot_preview_filename_matches_the_gid_iid_side_phase_convention(user_dir):
    gid, iid = AIG_TOWER
    path = paths.image_db_lots_path(gid, iid, "S", night=False)
    assert path.parent == paths.image_db_lots_dir()
    assert path.name == "0xa8fbd372-0xc6bb6905-S-D.png"


def test_night_flag_selects_the_n_phase_letter(user_dir):
    gid, iid = AIG_TOWER
    day = paths.image_db_lots_path(gid, iid, "E", night=False)
    night = paths.image_db_lots_path(gid, iid, "E", night=True)
    assert day.name == "0xa8fbd372-0xc6bb6905-E-D.png"
    assert night.name == "0xa8fbd372-0xc6bb6905-E-N.png"


def test_all_eight_views_of_a_lot_have_distinct_filenames(user_dir):
    gid, iid = AIG_TOWER
    names = {
        paths.image_db_lots_path(gid, iid, side, night=night).name for side in LOT_VIEW_SIDES for night in (False, True)
    }
    assert len(names) == 8


def test_gid_and_iid_are_masked_to_unsigned_32_bit(user_dir):
    path = paths.image_db_lots_path(-1, 0x1_0000_0000 | 0xABCD, "N", night=False)
    assert path.name == "0xffffffff-0x0000abcd-N-D.png"


def test_default_rotation_is_south_when_no_road_is_required():
    assert required_road_default_rotation(0) == 0
    assert LOT_VIEW_SIDES[0] == "S"


@pytest.mark.parametrize(
    ("bit", "edge"),
    ROAD_FLAG_EDGES,
)
def test_single_required_road_faces_its_own_edge(bit, edge):
    rotation = required_road_default_rotation(bit)
    assert rotation == EDGE_VIEW_ROTATION[edge]
    assert edge in road_edges_from_flags(bit)


def test_view_rotation_maps_each_edge_to_the_expected_compass_side():
    assert EDGE_VIEW_ROTATION == {
        EDGE_ZMAX: 0,  # Front  -> South
        EDGE_XMIN: 1,  # Left   -> West
        EDGE_ZMIN: 2,  # Behind -> North
        EDGE_XMAX: 3,  # Right  -> East
    }
    assert LOT_VIEW_SIDES == ("S", "W", "N", "E")


def test_corner_lot_prefers_the_south_view():
    # Left (bit 0) + Front (bit 3): the South/front edge wins over West.
    assert required_road_default_rotation(0b1001) == EDGE_VIEW_ROTATION[EDGE_ZMAX]
    # Left + Behind + Front (bits 0,1,3): South still wins over West and North.
    assert required_road_default_rotation(0b1011) == EDGE_VIEW_ROTATION[EDGE_ZMAX]
    # No South road -- Behind (bit 1) + Right (bit 2): Behind (-> North) wins.
    assert required_road_default_rotation(0b0110) == EDGE_VIEW_ROTATION[EDGE_ZMIN]
    # No South road -- Left (bit 0) + Behind (bit 1): Left (-> West) wins.
    assert required_road_default_rotation(0b0011) == EDGE_VIEW_ROTATION[EDGE_XMIN]


def test_malformed_road_flags_default_to_the_south_view():
    assert required_road_default_rotation(None) == 0
    assert required_road_default_rotation("not-an-int") == 0


def test_lot_preview_path_returns_a_pathlib_path(user_dir):
    assert isinstance(paths.image_db_lots_path(*AIG_TOWER, "W"), Path)
