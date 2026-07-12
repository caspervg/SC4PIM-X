import tomllib
from pathlib import Path

from sc4pimx import translation
from scripts.extract_category_translations import add_missing_categories, xml_categories


def test_english_catalog_covers_every_numeric_xml_category():
    root = Path(__file__).resolve().parents[1]
    with open(root / "assets/lang/en.toml", "rb") as handle:
        catalog = tomllib.load(handle)["categories"]
    translated = {int(str(key), 16) for key in catalog}
    expected = {category_id for category_id, _name in xml_categories(root / "assets/new_properties.xml")}
    # Historical catalog-only IDs may remain valid even after an XML revision.
    assert expected <= translated


def test_extractor_adds_only_missing_categories(tmp_path):
    xml = tmp_path / "properties.xml"
    xml.write_text(
        '<ROOT><CATEGORY ID="0x00000001" Name="XML one"/>'
        '<CATEGORY ID="0x00000002" Name="XML two"/></ROOT>',
        encoding="utf-8",
    )
    lang = tmp_path / "de.toml"
    lang.write_text('[categories]\n0x00000001 = "Übersetzt"\n', encoding="utf-8")

    assert add_missing_categories(xml, lang) == 1
    with open(lang, "rb") as handle:
        categories = tomllib.load(handle)["categories"]
    assert categories["0x00000001"] == "Übersetzt"
    assert categories["0x00000002"] == "XML two"
    assert add_missing_categories(xml, lang) == 0


def test_bundled_languages_have_display_names():
    assert translation.language_display_name("en") == "English"
    assert translation.language_display_name("de") == "Deutsch"


def test_main_app_keeps_translation_catalog_module_binding():
    from sc4pimx import SC4PIMApp

    assert SC4PIMApp.translation_catalog.DEFAULT_LANGUAGE == "en"
