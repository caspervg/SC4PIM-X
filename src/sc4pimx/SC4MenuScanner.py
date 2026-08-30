"""Submenu model: what submenus exist, how they nest, and what is in them.

Two sources feed the model:

* the curated ``Building Submenus`` (0xAA1DD399) option list in
  ``new_properties.xml`` -- the submenus the Submenus DLL ships with, grouped
  by the ``SubMenuROOT*`` HELP markers into the game's root toolbars;
* a scan of the loaded plugins for community-authored submenu *button*
  exemplars, which carry their own parent/order and therefore describe real
  nesting the curated list cannot.

The scan is memory-only by design: it walks ``virtual_dat.allEntries`` but only
looks at exemplars that already have a parsed ``.exemplar`` (i.e. text-format
'EQZT' exemplars, which the loader parses eagerly regardless of Exemplar Type
-- see ``SC4DatTools.SC4Exemplar.DecodeBinary``'s whole-exemplar skip for
binary 'EQZB' ones). That's also exactly where community-authored submenu
buttons live in practice; re-parsing every binary exemplar in a large plugins
folder just to find a handful of submenu buttons would be too slow for an
on-demand scan (see ``LotPropertiesDlg._list_retaining_wall_options`` for the
same scoping tradeoff).

Everything here is wx-free so the model can be exercised headlessly; the
dialogs (``SC4SubmenuTreeDlg``, ``SC4NewSubmenuDlg``, ``SC4SubmenuPatchDlg``,
``SC4BuildingSubmenuPicker``) render it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .textutil import decode_sc4_text

BUILDING_EXEMPLAR_TYPE = 0x6534284A
COHORT_TYPE = 0x05342861
EXEMPLAR_PATCH_GROUP = 0xB03697D1
PNG_ICON_TYPE = 0x856DDBAC
SUBMENU_BUTTON_GROUP = 0x2A3858E4
SUBMENU_BUTTON_KIND = 0x28  # Exemplar Type: Submenu Button

PROP_EXEMPLAR_TYPE = 0x10
PROP_EXEMPLAR_NAME = 0x20
PROP_EXEMPLAR_PATCH_TARGETS = 0x0062E78A
PROP_ITEM_ICON = 0x8A2602B8
PROP_ITEM_ORDER = 0x8A2602B9
PROP_ITEM_BUTTON_ID = 0x8A2602BB
PROP_ITEM_SUBMENU_PARENT_ID = 0x8A2602CA
PROP_ITEM_BUTTON_CLASS = 0x8A2602CC
PROP_USER_VISIBLE_NAME_KEY = 0x8A416A99
PROP_BUILDING_SUBMENUS = 0xAA1DD399

CATEGORY_BUILDING = 210746197
CATEGORY_FLORA = 1830116951

# The ``SubMenuROOT*`` markers in new_properties.xml name the game toolbar a
# curated submenu hangs off. They are display groupings, not button IDs -- the
# game's own root buttons are hardcoded in the executable and never appear as
# exemplars, so the tree shows them as grouping nodes rather than menus.
ROOT_LABELS = {
    "SubMenuROOTRCI": "RCI",
    "SubMenuROOTHighway": "Highway",
    "SubMenuROOTRail": "Rail",
    "SubMenuROOTMiscTransit": "Misc Transit",
    "SubMenuROOTWaterTransit": "Water Transit",
    "SubMenuROOTPowerUtility": "Power Utility",
    "SubMenuROOTCivicPolice": "Civic Police",
    "SubMenuROOTCivicEducation": "Civic Education",
    "SubMenuROOTCivicHealth": "Civic Health",
    "SubMenuROOTLandmarks": "Landmarks",
    "SubMenuROOTPark": "Parks",
}

SOURCE_BUILTIN = "builtin"
SOURCE_SCANNED = "scanned"

VIA_EXEMPLAR = "exemplar"
VIA_PATCH = "patch"

KIND_MENU = "menu"
KIND_ROOT = "root"
KIND_ORPHAN = "orphan"


@dataclass(frozen=True)
class ScannedMenu:
    value: int
    label: str
    parent_id: int
    item_order: int
    tgi: Optional[tuple] = None
    file_name: Optional[str] = None
    icon_id: Optional[int] = None


@dataclass(frozen=True)
class MenuEntry:
    """One submenu button, whether curated or discovered in the plugins."""

    value: int
    label: str
    parent_id: Optional[int]
    item_order: int
    root_group: Optional[str]
    source: str
    tgi: Optional[tuple] = None
    file_name: Optional[str] = None
    icon_id: Optional[int] = None

    @property
    def hex(self) -> str:
        return "0x%08X" % self.value


@dataclass(frozen=True)
class MenuMember:
    """A building or flora item that shows up in a submenu."""

    kind: str  # "building" or "flora"
    name: str
    tgi: tuple
    via: str  # VIA_EXEMPLAR (the item says so) or VIA_PATCH (a cohort says so)
    descriptor: object = None


@dataclass
class MenuTreeNode:
    key: str
    label: str
    kind: str
    entry: Optional[MenuEntry] = None
    children: list = field(default_factory=list)

    @property
    def value(self) -> Optional[int]:
        return self.entry.value if self.entry is not None else None


# -- cache ------------------------------------------------------------------


def _cache(virtual_dat) -> dict:
    cache = getattr(virtual_dat, "_submenu_cache", None)
    if cache is None:
        cache = {}
        try:
            virtual_dat._submenu_cache = cache
        except AttributeError:  # exotic/read-only stand-ins in tests
            return {}
    return cache


def invalidate_menu_cache(virtual_dat) -> None:
    """Drop every cached submenu view.

    Call this after writing a submenu button or a submenu patch so the next
    picker/tree/dropdown sees it without the user hitting "Refresh".
    """
    try:
        virtual_dat._submenu_cache = {}
    except AttributeError:
        pass
    # Legacy attribute from the first scanner revision; cleared so a stale one
    # left on a long-lived VirtualDat cannot resurrect old results.
    try:
        virtual_dat._scanned_menus_cache = None
    except AttributeError:
        pass


# -- scanning ---------------------------------------------------------------


def resolve_display_name(virtual_dat, exemplar):
    """The name the game shows for an exemplar, or None.

    Prefers the User Visible Name Key, which points at the LTEXT the menu
    draws, and falls back to the internal Exemplar Name.
    """
    key = exemplar.GetProp(PROP_USER_VISIBLE_NAME_KEY)
    if key and tuple(key) != (0, 0, 0):
        entry = virtual_dat.getEntry(key[0], key[1], key[2])
        if entry is not None:
            try:
                if entry.content is None:
                    entry.read_file(None, True, True)
                return decode_sc4_text(entry.content[4:])
            except Exception:
                pass
    name = exemplar.GetProp(PROP_EXEMPLAR_NAME)
    return name[0] if name else None


def scan_menus(virtual_dat, force=False):
    """{button_id: ScannedMenu} for every discoverable custom submenu button.

    Cached on the virtual_dat instance; pass ``force=True`` to rescan (e.g. a
    "Refresh known menus" button after loading more plugins).
    """
    cache = _cache(virtual_dat)
    cached = cache.get("scanned")
    if cached is not None and not force:
        return cached
    menus = {}
    for entry in virtual_dat.allEntries:
        if (entry.tgi[0] != BUILDING_EXEMPLAR_TYPE
                or entry.tgi[1] != SUBMENU_BUTTON_GROUP):
            continue
        exemplar = getattr(entry, "exemplar", None)
        if exemplar is None:
            continue
        exemplar_type = exemplar.GetProp(PROP_EXEMPLAR_TYPE)
        if not exemplar_type or exemplar_type[0] != SUBMENU_BUTTON_KIND:
            continue
        parent = exemplar.GetProp(PROP_ITEM_SUBMENU_PARENT_ID)
        if not parent:
            continue
        icon = exemplar.GetProp(PROP_ITEM_ICON)
        button_id = exemplar.GetProp(PROP_ITEM_BUTTON_ID) or icon
        value = int(button_id[0]) if button_id else entry.tgi[2]
        name = resolve_display_name(virtual_dat, exemplar) or ("0x%08X" % value)
        order = exemplar.GetProp(PROP_ITEM_ORDER)
        menus[value] = ScannedMenu(
            value=value, label=name, parent_id=int(parent[0]),
            item_order=int(order[0]) if order else 0,
            tgi=tuple(entry.tgi), file_name=getattr(entry, "fileName", None),
            icon_id=int(icon[0]) if icon else None,
        )
    cache["scanned"] = menus
    cache.pop("entries", None)
    return menus


def builtin_menus(virtual_dat):
    """{button_id: MenuEntry} for the submenus new_properties.xml documents."""
    prop_def = virtual_dat.properties.get(PROP_BUILDING_SUBMENUS)
    options = dict(getattr(prop_def, "Options", {}) or {}) if prop_def is not None else {}
    groups = dict(getattr(prop_def, "OptionGroups", {}) or {}) if prop_def is not None else {}
    entries = {}
    for value, label in options.items():
        try:
            value = int(value)
        except (TypeError, ValueError):
            continue
        entries[value] = MenuEntry(
            value=value, label=label, parent_id=None, item_order=0,
            root_group=groups.get(value) or None, source=SOURCE_BUILTIN,
        )
    return entries


def menu_entries(virtual_dat, force=False):
    """{button_id: MenuEntry} merging the curated list with the plugins scan.

    Curated labels win (they are human-curated and stable); parent/order/TGI
    come from the scan when the same button was also found on disk.
    """
    cache = _cache(virtual_dat)
    cached = cache.get("entries")
    if cached is not None and not force:
        return cached
    entries = builtin_menus(virtual_dat)
    for value, menu in scan_menus(virtual_dat, force=force).items():
        known = entries.get(value)
        if known is None:
            entries[value] = MenuEntry(
                value=value, label=menu.label, parent_id=menu.parent_id,
                item_order=menu.item_order, root_group=None, source=SOURCE_SCANNED,
                tgi=menu.tgi, file_name=menu.file_name, icon_id=menu.icon_id,
            )
        else:
            entries[value] = MenuEntry(
                value=value, label=known.label, parent_id=menu.parent_id,
                item_order=menu.item_order, root_group=known.root_group,
                source=known.source, tgi=menu.tgi, file_name=menu.file_name,
                icon_id=menu.icon_id,
            )
    cache["entries"] = entries
    return entries


def menu_options(virtual_dat, force=False):
    """{button_id: label} for the parent-menu dropdowns."""
    return {value: entry.label for value, entry in menu_entries(virtual_dat, force=force).items()}


# -- membership -------------------------------------------------------------


def _category_descriptors(virtual_dat, category_id):
    categories = getattr(virtual_dat, "categories", None) or {}
    category = categories.get(category_id)
    if category is None:
        return ()
    return getattr(category, "descriptors", ()) or ()


def menu_members(virtual_dat, force=False):
    """{button_id: [MenuMember]} for every building/flora assigned to a submenu.

    Covers both ways an item lands in a menu: the item's own property, and a
    standalone patch cohort that targets it (what "Add to Submenu (Patch)"
    writes). Cached like the rest of the model.
    """
    cache = _cache(virtual_dat)
    cached = cache.get("members")
    if cached is not None and not force:
        return cached

    members = {}
    seen = set()  # (button_id, tgi) so a patch cannot double-list an item
    by_tgi = {}

    def add(value, member):
        try:
            value = int(value) & 0xFFFFFFFF
        except (TypeError, ValueError):
            return
        if (value, member.tgi) in seen:
            return
        seen.add((value, member.tgi))
        members.setdefault(value, []).append(member)

    for category_id, kind, prop_id in (
        (CATEGORY_BUILDING, "building", PROP_BUILDING_SUBMENUS),
        (CATEGORY_FLORA, "flora", PROP_ITEM_SUBMENU_PARENT_ID),
    ):
        for descriptor in _category_descriptors(virtual_dat, category_id):
            exemplar = getattr(descriptor, "exemplar", None)
            entry = getattr(exemplar, "entry", None)
            if entry is None:
                continue
            tgi = tuple(entry.tgi)
            if tgi in by_tgi:
                continue
            by_tgi[tgi] = (kind, descriptor)
            values = exemplar.GetProp(prop_id)
            if not values:
                continue
            for value in values:
                add(value, MenuMember(kind=kind, name=str(descriptor.name), tgi=tgi,
                                      via=VIA_EXEMPLAR, descriptor=descriptor))

    for entry in getattr(virtual_dat, "cohorts", ()) or ():
        tgi = tuple(getattr(entry, "tgi", ()) or ())
        if len(tgi) < 2 or (int(tgi[1]) & 0xFFFFFFFF) != EXEMPLAR_PATCH_GROUP:
            continue
        exemplar = getattr(entry, "exemplar", None)
        if exemplar is None:
            continue
        targets = exemplar.GetProp(PROP_EXEMPLAR_PATCH_TARGETS)
        if not targets or len(targets) < 2:
            continue
        values = exemplar.GetProp(PROP_BUILDING_SUBMENUS) or exemplar.GetProp(PROP_ITEM_SUBMENU_PARENT_ID)
        if not values:
            continue
        for offset in range(0, len(targets) - 1, 2):
            tgi = (BUILDING_EXEMPLAR_TYPE, int(targets[offset]) & 0xFFFFFFFF,
                   int(targets[offset + 1]) & 0xFFFFFFFF)
            kind, descriptor = by_tgi.get(tgi, ("building", None))
            name = str(descriptor.name) if descriptor is not None else "0x%08X-0x%08X" % (tgi[1], tgi[2])
            for value in values:
                add(value, MenuMember(kind=kind, name=name, tgi=tgi,
                                      via=VIA_PATCH, descriptor=descriptor))

    for bucket in members.values():
        bucket.sort(key=lambda m: (m.kind, m.name.lower()))
    cache["members"] = members
    return members


def member_count(members, value) -> int:
    return len(members.get(value, ())) if members else 0


# -- icons ------------------------------------------------------------------


def _png_icon_index(virtual_dat):
    """{instance: entry} over every PNG icon, built once per cache generation.

    Menu icons are addressed by instance alone (the group is up to whoever
    authored the pack), so a lookup by TGI only works for icons this app wrote.
    """
    cache = _cache(virtual_dat)
    index = cache.get("png_icons")
    if index is None:
        index = {}
        for entry in getattr(virtual_dat, "allEntries", ()) or ():
            if entry.tgi[0] == PNG_ICON_TYPE:
                index.setdefault(entry.tgi[2], entry)
        cache["png_icons"] = index
    return index


def menu_icon_entry(virtual_dat, entry):
    """The PNG entry a menu's button points at, or None."""
    icon_id = entry.icon_id if entry.icon_id is not None else entry.value
    if entry.tgi is not None:
        exact = virtual_dat.getEntry(PNG_ICON_TYPE, entry.tgi[1], icon_id)
        if exact is not None:
            return exact
    return _png_icon_index(virtual_dat).get(icon_id)


def menu_icon_png(virtual_dat, entry):
    """Raw PNG bytes for a menu's icon, or None. No image decoding here.

    A PNG entry is never eagerly read at load time, so ``content`` is usually
    absent rather than None -- and when it is present the entry may still hold
    only the compressed bytes. Both cases go through ``read_file``, the same
    dance ``SC4LETools.FillListForIcon`` does.
    """
    icon_entry = menu_icon_entry(virtual_dat, entry)
    if icon_entry is None:
        return None
    try:
        if getattr(icon_entry, "content", None) is None:
            icon_entry.rawContent = None
            icon_entry.read_file(None, True, True)
        content = getattr(icon_entry, "content", None)
        return bytes(content) if content else None
    except Exception:
        return None


# -- tree -------------------------------------------------------------------


def root_label(group: Optional[str]) -> str:
    if not group:
        return ""
    return ROOT_LABELS.get(group, group.replace("SubMenuROOT", "") or group)


def _sorted_children(entries, values):
    return sorted(values, key=lambda v: (entries[v].item_order, entries[v].label.lower(), v))


def build_menu_tree(entries, ungrouped_label="Ungrouped", orphan_label="Game menu %s"):
    """Roots of the submenu tree, as ``MenuTreeNode`` objects.

    A menu nests under another menu when its parent button ID is one we know
    about. Everything else is bucketed: curated menus by their ``SubMenuROOT*``
    marker, discovered menus whose parent is a hardcoded game toolbar button by
    that parent's ID.
    """
    children = {value: [] for value in entries}
    by_group = {}
    orphans = {}
    ungrouped = []

    for value, entry in entries.items():
        parent = entry.parent_id
        if parent is not None and parent != value and parent in entries:
            children[parent].append(value)
        elif entry.root_group:
            by_group.setdefault(entry.root_group, []).append(value)
        elif parent:
            orphans.setdefault(int(parent) & 0xFFFFFFFF, []).append(value)
        else:
            ungrouped.append(value)

    def build(value, seen):
        entry = entries[value]
        node = MenuTreeNode(key="menu:0x%08X" % value, label=entry.label, kind=KIND_MENU, entry=entry)
        if value in seen:
            return node
        seen = seen | {value}
        for child in _sorted_children(entries, children[value]):
            node.children.append(build(child, seen))
        return node

    roots = []
    ordered_groups = [g for g in ROOT_LABELS if g in by_group]
    ordered_groups += sorted(g for g in by_group if g not in ROOT_LABELS)
    for group in ordered_groups:
        node = MenuTreeNode(key="root:%s" % group, label=root_label(group), kind=KIND_ROOT)
        node.children = [build(v, frozenset()) for v in _sorted_children(entries, by_group[group])]
        roots.append(node)

    for parent in sorted(orphans):
        node = MenuTreeNode(key="orphan:0x%08X" % parent, label=orphan_label % ("0x%08X" % parent),
                            kind=KIND_ORPHAN)
        node.children = [build(v, frozenset()) for v in _sorted_children(entries, orphans[parent])]
        roots.append(node)

    if ungrouped:
        node = MenuTreeNode(key="root:", label=ungrouped_label, kind=KIND_ROOT)
        node.children = [build(v, frozenset()) for v in _sorted_children(entries, ungrouped)]
        roots.append(node)

    return roots


def menu_path(entries, value, separator=" > "):
    """Human-readable ancestry of a menu, e.g. ``"Parks > Plazas > Fountains"``."""
    parts = []
    seen = set()
    current = value
    while current in entries and current not in seen:
        seen.add(current)
        entry = entries[current]
        parts.append(entry.label)
        current = entry.parent_id
    if not parts:
        return "0x%08X" % (int(value) & 0xFFFFFFFF)
    entry = entries.get(value)
    if entry is not None and entry.root_group and len(parts) == 1:
        # Prefix the toolbar the menu sits on, unless it is named after it
        # ("Parks > Parks" reads worse than plain "Parks").
        group = root_label(entry.root_group)
        if group and group != parts[0]:
            parts.append(group)
    return separator.join(reversed(parts))
