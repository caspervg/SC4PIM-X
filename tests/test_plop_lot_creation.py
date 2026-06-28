import ast
import inspect
import textwrap

from sc4pimx.SC4PIMApp import (
    _PLOP_LOT_AIRPORT_CATEGORY,
    _PLOP_LOT_MUNICIPAL_AIRPORT_CATEGORY,
    _PLOP_LOT_SEAPORT_CATEGORY,
    NoteBookPanel,
    _plop_lot_configuration,
)


def category_matcher(*category_ids):
    matches = set(category_ids)
    return matches.__contains__


def test_plop_lot_configuration_for_regular_ploppable():
    assert _plop_lot_configuration(category_matcher()) == (255, 15, (0,))


def test_plop_lot_configuration_for_seaport():
    matches = category_matcher(_PLOP_LOT_SEAPORT_CATEGORY, 0xCCB23925)
    assert _plop_lot_configuration(matches) == (5, 12, (0,))


def test_plop_lot_configuration_for_municipal_airport_size_one():
    matches = category_matcher(
        _PLOP_LOT_AIRPORT_CATEGORY,
        _PLOP_LOT_MUNICIPAL_AIRPORT_CATEGORY,
        0x7FF36953,
    )
    assert _plop_lot_configuration(matches) == (1, 11, (1, 2, 3))


def test_plop_lot_configuration_for_airport():
    matches = category_matcher(_PLOP_LOT_AIRPORT_CATEGORY, 0x0C8FBD49)
    assert _plop_lot_configuration(matches) == (2, 11, (1, 2, 3))


def test_plop_lot_write_and_idk_copy_are_not_nested_under_uvnk():
    source = textwrap.dedent(inspect.getsource(NoteBookPanel.OnCreatePlopLot))
    tree = ast.parse(source)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    write_call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'WriteADat'
    )
    ancestors = []
    current = write_call
    while current in parents:
        current = parents[current]
        ancestors.append(current)

    uvnk_if = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and 'UVNK' in {name.id for name in ast.walk(node.test) if isinstance(name, ast.Name)}
    )
    guarded_names = {name.id for statement in uvnk_if.body for name in ast.walk(statement) if isinstance(name, ast.Name)}

    assert not any(isinstance(node, ast.If) for node in ancestors)
    assert 'IDK' not in guarded_names
