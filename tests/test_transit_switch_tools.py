import pytest

from sc4pimx import SC4TransitSwitchTools as tsw


def test_raw_switch_text_accepts_reader_style_commas():
    assert tsw.parse_switch_bytes_text("0x81,0xF0,0x00,0x00") == [0x81, 0xF0, 0x00, 0x00]


def test_raw_switch_text_accepts_whitespace_and_unprefixed_hex():
    assert tsw.parse_switch_bytes_text("81 F0 00 00\n82;A0;02;00") == [
        0x81,
        0xF0,
        0x00,
        0x00,
        0x82,
        0xA0,
        0x02,
        0x00,
    ]


def test_raw_switch_text_keeps_expert_rows_editable():
    rows = tsw.decode_switch_array(tsw.parse_switch_bytes_text("0x99,0xF1,0xFE,0x7F"))

    assert len(rows) == 1
    assert rows[0].expert
    assert rows[0].as_bytes() == (0x99, 0xF1, 0xFE, 0x7F)


def test_raw_switch_text_rejects_partial_rows():
    with pytest.raises(ValueError, match="multiple of 4"):
        tsw.parse_switch_bytes_text("0x81,0xF0,0x00")


def test_raw_switch_text_rejects_out_of_range_bytes():
    with pytest.raises(ValueError, match="0xFF"):
        tsw.parse_switch_bytes_text("0x81,0x100,0x00,0x00")


def test_switch_bytes_format_uses_reader_style_hex():
    assert tsw.format_switch_bytes([0x81, 0xF0, 0x00, 0x02]) == "0x81,0xF0,0x00,0x02"
