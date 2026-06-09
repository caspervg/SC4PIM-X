from sc4pimx.textutil import decode_sc4_string_prop, decode_sc4_text, encode_sc4_text


def test_decode_sc4_string_prop_decodes_bytes_without_repr_wrapper():
    assert decode_sc4_string_prop(b"Some item name") == "Some item name"


def test_decode_sc4_string_prop_preserves_latin1_bytes():
    assert decode_sc4_string_prop(b"Caf\xe9") == "Caf\xe9"


def test_sc4_ltext_round_trip_uses_utf16_le_payload():
    text = "Some item name"
    assert decode_sc4_text(encode_sc4_text(text)) == text
