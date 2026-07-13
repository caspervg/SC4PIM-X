import os
from types import SimpleNamespace

import pytest

from sc4pimx import config
from sc4pimx.ConvertLotBuildingDlg import (
    MODE_CLONE,
    MODE_OVERRIDE,
    suggested_conversion_name,
)
from sc4pimx.SC4Data import conversion_target_kind, list_convertible_categories
from sc4pimx.SC4PIMApp import (
    SC4NoteBook,
    _allocate_conversion_iid,
    _conversion_filename_stem,
    _conversion_lot_configuration,
    _conversion_pair_tgis,
    _converted_lot_row_values,
    _override_output_directory,
    _source_building_candidates,
)


def category(category_id, name, parent=None, rules=False):
    item = SimpleNamespace(
        ID=category_id,
        Name=name,
        parent=parent,
        childs=[],
        setProperties={0x10: 'value'} if rules else {},
        factorProperties={},
        pairedFactorProperties={},
        programProperties={},
        evalProperties={},
        code=[],
    )
    if parent is not None:
        parent.childs.append(item)
    return item


def test_convertible_categories_are_leaf_rules_under_supported_branches():
    root = category(0x0C8FBB55, 'Building')
    growable = category(0xAC8FBB73, 'Growable', root)
    residential = category(0x101, 'Residential', growable, rules=True)
    ploppable = category(0xCC8FBC2D, 'Ploppable', root)
    civic = category(0x102, 'Civic', ploppable)
    garage = category(0x103, 'Garage', civic, rules=True)
    category(0x104, 'No rules', civic)
    category(0xD30E71DF, 'Unknown', ploppable, rules=True)
    category(0xCC8ABC2D, 'Unused', root, rules=True)

    choices = list_convertible_categories(root)

    assert [(choice.category, choice.breadcrumb, choice.target_kind) for choice in choices] == [
        (residential, ('Growable', 'Residential'), 'growable'),
        (garage, ('Ploppable', 'Civic', 'Garage'), 'ploppable'),
    ]
    assert conversion_target_kind(garage) == 'ploppable'


def test_convertible_categories_reject_wrong_root():
    assert list_convertible_categories(category(0x12345678, 'Not Building')) == []


def test_ploppable_conversion_preserves_every_row_shape_and_te_switch():
    rows = [
        (0x88EDC900, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0x11111111]),
        (0x88EDC901, [7, 42, 43, 44, 45]),
        (0x88EDC902, [2, 99]),
    ]

    converted, removed = _converted_lot_row_values(rows, 0x22222222, True)

    assert converted[0][1][12] == 0x22222222
    assert converted[1:] == rows[1:]
    assert removed == 0
    assert rows[0][1][12] == 0x11111111  # source data is not mutated


def test_growable_conversion_removes_only_te_rows():
    rows = [
        (0x88EDC900, [0] + [0] * 11 + [0x11111111]),
        (0x88EDC901, [7, 1, 2]),
        (0x88EDC902, [1, 3, 4, 5]),
    ]

    converted, removed = _converted_lot_row_values(rows, 0x22222222, False)

    assert [prop_id for prop_id, _ in converted] == [0x88EDC900, 0x88EDC902]
    assert converted[0][1][12] == 0x22222222
    assert removed == 1


def test_conversion_requires_exactly_one_building_row():
    with pytest.raises(ValueError, match='exactly one'):
        _converted_lot_row_values([(0x88EDC900, [2, 0])], 1, True)


def test_family_lot_resolves_concrete_members_and_prefers_clicked_building():
    family_iid = 0x5F3759DF

    def descriptor(name, iid):
        entry = SimpleNamespace(tgi=(0x6534284A, 0x11111111, iid))
        exemplar = SimpleNamespace(entry=entry, GetProp=lambda prop_id: [2] if prop_id == 16 else None)
        return SimpleNamespace(name=name, exemplar=exemplar)

    alpha = descriptor('Alpha', 0x100)
    beta = descriptor('Beta', 0x200)
    root = SimpleNamespace(descriptors=[alpha, beta])
    family = SimpleNamespace(descriptors=[alpha, beta])
    virtual_dat = SimpleNamespace(categories={0x0C8FBB55: root, family_iid: family})
    lot = SimpleNamespace(GetPropRange=lambda low, high: {
        0x88EDC900: [0] + [0] * 11 + [family_iid]
    })

    assert _source_building_candidates(virtual_dat, lot, beta.exemplar) == [beta, alpha]


def test_iid_allocator_checks_every_resource_prefix():
    occupied = {(0x6534284A, 0x11111111, 0x100), (0x856DDBAC, 0x6A386D26, 0x200)}
    virtual_dat = SimpleNamespace(getEntry=lambda t, g, i: object() if (t, g, i) in occupied else None)
    candidates = iter((0x100, 0x200, 0x300))

    result = _allocate_conversion_iid(
        virtual_dat,
        ((0x6534284A, 0x11111111), (0x856DDBAC, 0x6A386D26)),
        candidate_factory=lambda: next(candidates),
    )

    assert result == 0x300


def test_override_reuses_original_pair_tgis_but_clone_uses_author_gid_and_new_iid():
    source_building = (0x6534284A, 0x11111111, 0x22222222)
    source_lot = (0x6534284A, 0xA8FBD372, 0x33333333)

    assert _conversion_pair_tgis(source_building, source_lot, 0x44444444, True) == (
        source_building, source_lot,
    )
    assert _conversion_pair_tgis(source_building, source_lot, 0x44444444, False, 0x55555555) == (
        (0x6534284A, 0x44444444, 0x55555555),
        (0x6534284A, 0xA8FBD372, 0x55555555),
    )


def test_conversion_filename_templates_are_compact_and_strip_package_extensions():
    values = dict(
        name='Functional Garage', source='Modular Parking', category='Garage',
        gid=0x1234, building_iid=0xABCD, lot_iid=0x5678,
    )

    assert _conversion_filename_stem(
        '{name}_Converted_{lot_iid}.SC4Lot', **values
    ) == 'Functional Garage_Converted_00005678'
    assert _conversion_filename_stem(
        '{source}_Override.dat', **values
    ) == 'Modular Parking_Override'


def test_unknown_conversion_filename_placeholder_is_reported():
    with pytest.raises(ValueError, match='unknown placeholder'):
        _conversion_filename_stem(
            '{missing}', name='Name', source='Source', category='Garage',
            gid=1, building_iid=2, lot_iid=3,
        )


def test_override_directory_is_relative_to_plugins_and_cannot_escape(tmp_path):
    plugins = tmp_path / 'Plugins'
    plugins.mkdir()

    target = _override_output_directory(plugins, '895-my-overrides')

    assert target == str((plugins / '895-my-overrides').resolve())
    assert (plugins / '895-my-overrides').is_dir()
    with pytest.raises(ValueError, match='cannot escape'):
        _override_output_directory(plugins, os.path.join('..', 'outside'), create=False)


def test_conversion_config_defaults_and_user_overrides(monkeypatch, tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text(
        '[Conversion]\nOverrideLotBuildingFilename = "Custom_{source}"\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(config, 'config_path', lambda: path)

    settings = config.load_conversion()

    assert settings['ConvertedLotBuildingFilename'] == '{source}_Converted_{lot_iid}'
    assert settings['OverrideLotBuildingFilename'] == 'Custom_{source}'
    assert settings['OverrideOutputDirectory'] == '895-my-overrides'


def test_suggested_exemplar_names_distinguish_copy_and_override():
    assert suggested_conversion_name('Modular Parking', MODE_CLONE) == 'Modular Parking (Converted)'
    assert suggested_conversion_name('Modular Parking', MODE_OVERRIDE) == 'Modular Parking (Override)'


def test_open_override_tab_refreshes_to_authoritative_descriptor():
    tgi = (0x6534284A, 0x11111111, 0x22222222)
    old_entry = SimpleNamespace(tgi=tgi)
    new_entry = SimpleNamespace(tgi=tgi)
    old_descriptor = SimpleNamespace(
        name='Old', exemplar=SimpleNamespace(entry=old_entry)
    )
    new_descriptor = SimpleNamespace(
        name='New', exemplar=SimpleNamespace(entry=new_entry)
    )
    calls = []
    panel = SimpleNamespace(
        listProperties=SimpleNamespace(DeleteAllItems=lambda: calls.append('delete')),
        bSave=SimpleNamespace(Enable=lambda enabled: calls.append(('save', enabled))),
        FillTheList=lambda: calls.append('fill'),
    )
    notebook = SimpleNamespace(
        descriptors=[old_descriptor],
        GetPage=lambda index: panel,
        SetPageText=lambda index, text: calls.append(('title', index, text)),
    )
    virtual_dat = SimpleNamespace(getEntry=lambda *candidate: new_entry)

    refreshed = SC4NoteBook.RefreshOpenDescriptor(
        notebook, new_descriptor, virtual_dat
    )

    assert refreshed
    assert notebook.descriptors == [new_descriptor]
    assert panel.descriptor is new_descriptor
    assert panel.exemplar is new_descriptor.exemplar
    assert ('save', False) in calls
    assert ('title', 0, 'New') in calls

    # Re-refreshing an already authoritative descriptor must still repair a
    # stale visible tab label.
    calls.clear()
    assert SC4NoteBook.RefreshOpenDescriptor(notebook, new_descriptor, virtual_dat)
    assert calls == [('title', 0, 'New')]


def test_regular_ploppable_target_uses_ploppable_lot_fields():
    root = category(0x0C8FBB55, 'Building')
    ploppable = category(0xCC8FBC2D, 'Ploppable', root)
    garage = category(0x101, 'Garage', ploppable, rules=True)

    result = _conversion_lot_configuration(None, None, garage, (2, 3))

    assert result == {
        'kind': 'ploppable',
        'stage': 255,
        'zoning': (15,),
        'wealth': (0,),
        'purpose': (0,),
    }


def test_seaport_target_applies_its_required_zero_foundation_slope():
    root = category(0x0C8FBB55, 'Building')
    ploppable = category(0xCC8FBC2D, 'Ploppable', root)
    seaport = category(0xCCB2391F, 'Seaport', ploppable)
    stage_five = category(0xCCB23925, 'Stage 5', seaport, rules=True)

    result = _conversion_lot_configuration(None, None, stage_five, (4, 6))

    assert result['stage'] == 5
    assert result['zoning'] == (12,)
    assert result['max_slope_before_foundation'] == (0.0,)


def test_agricultural_field_target_does_not_require_occupant_groups():
    root = category(0x0C8FBB55, 'Building')
    field = category(0x2CAA4E2A, 'Agricultural Field', root, rules=True)
    building = SimpleNamespace(GetProp=lambda prop_id: [12.0, 5.0, 12.0])
    virtual_dat = SimpleNamespace(ComputeZoning=lambda purpose, height: [4, 5])

    result = _conversion_lot_configuration(virtual_dat, building, field, (1, 1))

    assert result == {
        'kind': 'growable',
        'stage': 1,
        'zoning': (4, 5),
        'wealth': (1,),
        'purpose': (5,),
    }
