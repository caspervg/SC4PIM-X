"""Transit-preset wizard for the building-exemplar editor.

Wraps the existing ``<CATEGORY>`` auto-fill machinery (see
``build_category_props_for_preset`` in ``SC4PIMApp``) and surfaces every
category tagged ``WizardType="TransitPreset"`` in ``new_properties.xml`` as
a user-applicable preset. The user can optionally:

* flip a preset between proximity (network beside the lot, edges = ``0xF0``)
  and on-top with through-traffic in N-S (edges = ``0x50``) or W-E
  (edges = ``0xA0``) -- rewrites byte 1 of every TSEC row whose
  ``from`` and ``to`` travel types are both the preset's "through" network;
* force Walk↔Subway switches in (per MGB's suggestion to dodge untested
  no-subway combinations);
* override the Traffic Capacity (``0xE90E25A3``) with a literal value
  instead of the preset's formula.

The preview pane re-runs the pipeline against the current exemplar each
time the user toggles an override, so "what you see is what gets written".

WizardType="TransitPreset" is one slot in a deliberately extensible
attribute: future wizard kinds (e.g. lot templates, family seeds) can mark
categories without another schema change.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

import wx

from . import SC4TransitSwitchTools as tsw
from .translation import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

PRESET_TYPE_TRANSIT = "Transit"


# --- Public helpers --------------------------------------------------------


def list_transit_presets(virtual_dat) -> list:
    """Return every ``<PRESET Type="Transit">`` declared anywhere in
    ``new_properties.xml``, paired with the category it lives under.

    Sorted by parent-category name / category name / preset name so the
    dropdown reads predictably.
    """
    out = []
    for category in virtual_dat.categories.values():
        for preset in getattr(category, "presets", []) or []:
            if getattr(preset, "Type", "") == PRESET_TYPE_TRANSIT:
                out.append((category, preset))
    out.sort(
        key=lambda cp: (
            (cp[0].parent.Name if cp[0].parent is not None else ""),
            cp[0].Name,
            cp[1].Name,
        )
    )
    return out


def build_eval_scope(virtual_dat, exemplar, app_GID: int) -> Optional[dict]:
    """Build an eval scope dict the way ``OnRebuildProperties`` does.

    Returns ``None`` when the exemplar is missing the ``Occupant Size``
    property (``0x27812820`` -> id 662775824); without that we cannot
    compute ``Volume`` and any TSCap formula would fail.
    """
    size = exemplar.GetProp(662775824)
    if size is None or len(size) < 3:
        return None
    Width = float(size[0])
    Height = float(size[1])
    Depth = float(size[2])
    try:
        fillingDegree = exemplar.GetProp(662775825)[0]
    except Exception:
        fillingDegree = 0.5
    name_prop = exemplar.GetProp(32)
    exemplarName = name_prop[0] if name_prop else ""

    LotSizeX = 1
    LotSizeY = 1
    try:
        lot_size = exemplar.GetProp(2297284496)
        if lot_size is not None and len(lot_size) >= 2:
            LotSizeX = lot_size[0]
            LotSizeY = lot_size[1]
        else:
            lot_desc = virtual_dat.FindLotFromBuilding(exemplar)
            if lot_desc is not None:
                lot_size = lot_desc.exemplar.GetProp(2297284496)
                if lot_size is not None and len(lot_size) >= 2:
                    LotSizeX = lot_size[0]
                    LotSizeY = lot_size[1]
    except Exception:
        logger.exception("Could not resolve LotSize for preset eval scope")

    Volume = Height * Width * Depth * fillingDegree
    return {
        "Height": Height,
        "height": Height,
        "Width": Width,
        "width": Width,
        "Depth": Depth,
        "depth": Depth,
        "Volume": Volume,
        "volume": Volume,
        "LotSizeX": LotSizeX,
        "LotSizeY": LotSizeY,
        "fillingDegree": fillingDegree,
        "IID": exemplar.entry.tgi[2],
        "GID": app_GID,
        "exemplarName": exemplarName,
    }


# --- Prop-string post-processing for overrides -----------------------------

_PROP_LINE_RE = re.compile(r'^0x([0-9a-fA-F]{8}):\{"([^"]*)"\}=([A-Za-z0-9]+):(\d+):\((.*)\)$')


def _parse_prop_line(line: str):
    """Split a ``CreateAPropFromString`` line into its components.

    Returns ``(id_int, name, type_str, count, values_str)`` or ``None`` if
    the line doesn't match the expected shape.
    """
    m = _PROP_LINE_RE.match(line)
    if m is None:
        return None
    return (int(m.group(1), 16), m.group(2), m.group(3), int(m.group(4)), m.group(5))


def _find_through_travel(rows: list[tsw.SwitchRow]) -> Optional[int]:
    """The "through-network" is the non-Walk travel type that pairs with
    itself in the preset (e.g. ElTrain↔ElTrain for an El Rail station).
    Returns the first such travel type byte, or ``None`` if the preset has
    no through-traffic (a pure proximity preset like Bus Stop, where Bus
    only ever pairs with Walk).
    """
    for row in rows:
        if row.frm == row.to and row.frm != tsw.TRAVEL_WALK:
            return row.frm
    return None


def _apply_orientation_override(
    rows: list[tsw.SwitchRow],
    orientation_mask: int,
) -> list[tsw.SwitchRow]:
    """Rewrite byte 1 of every through-network self-pair row.

    No-op when the preset has no through-traffic. Leaves Walk-bridge rows
    (Walk↔X) on ``0xF0`` -- only the self-pair gets the directional mask.
    """
    through = _find_through_travel(rows)
    if through is None:
        return rows
    out = []
    for row in rows:
        if row.frm == through and row.to == through and not row.expert:
            out.append(
                tsw.SwitchRow(
                    art=row.art,
                    edges=orientation_mask,
                    frm=row.frm,
                    to=row.to,
                )
            )
        else:
            out.append(row)
    return out


def _ensure_subway_walk_pair(rows: list[tsw.SwitchRow]) -> list[tsw.SwitchRow]:
    """Add Walk→Subway and Subway→Walk all-sides switches if absent."""
    has_out_in = any(
        (r.art == tsw.ART_OUTSIDE_TO_INSIDE and r.frm == tsw.TRAVEL_SUBWAY and r.to == tsw.TRAVEL_WALK)
        or (r.art == tsw.ART_OUTSIDE_TO_INSIDE and r.frm == tsw.TRAVEL_WALK and r.to == tsw.TRAVEL_SUBWAY)
        for r in rows
    )
    has_in_out = any(
        (r.art == tsw.ART_INSIDE_TO_OUTSIDE and r.frm == tsw.TRAVEL_SUBWAY and r.to == tsw.TRAVEL_WALK)
        or (r.art == tsw.ART_INSIDE_TO_OUTSIDE and r.frm == tsw.TRAVEL_WALK and r.to == tsw.TRAVEL_SUBWAY)
        for r in rows
    )
    extra: list[tsw.SwitchRow] = []
    if not has_out_in:
        extra.append(
            tsw.SwitchRow(
                art=tsw.ART_OUTSIDE_TO_INSIDE,
                edges=tsw.EDGE_BITS_ALL,
                frm=tsw.TRAVEL_SUBWAY,
                to=tsw.TRAVEL_WALK,
            )
        )
    if not has_in_out:
        extra.append(
            tsw.SwitchRow(
                art=tsw.ART_INSIDE_TO_OUTSIDE,
                edges=tsw.EDGE_BITS_ALL,
                frm=tsw.TRAVEL_WALK,
                to=tsw.TRAVEL_SUBWAY,
            )
        )
    return rows + extra


def _rewrite_tsec_line(virtual_dat, line: str, rows: list[tsw.SwitchRow]) -> str:
    """Replace the value list of a Transit Switch Point prop line."""
    from .SC4Data import CreateAPropFromString

    encoded = tsw.encode_switch_array(rows)
    # Match the original formatter: hex2str returns '0x%02x' for size=8.
    values = ",".join("0x%02x" % b for b in encoded)
    return CreateAPropFromString(virtual_dat.properties[tsw.PROP_TRANSIT_SWITCH_POINT], values)


def _rewrite_float_line(virtual_dat, prop_id: int, value: float) -> str:
    from .SC4Data import CreateAPropFromString

    return CreateAPropFromString(virtual_dat.properties[prop_id], str(float(value)))


def apply_overrides(
    virtual_dat,
    prop_lines: Iterable[str],
    orientation_mask: Optional[int],
    add_subway_walk: bool,
    override_cost: Optional[float],
    override_capacity: Optional[float],
) -> list[str]:
    """Post-process the generated prop strings according to the user's
    overrides. Returns a new list of prop strings ready for AddTextProp.
    """
    output: list[str] = []
    for line in prop_lines:
        parsed = _parse_prop_line(line)
        if parsed is None:
            output.append(line)
            continue
        prop_id, _name, _type, _count, values_str = parsed
        if prop_id == tsw.PROP_TRANSIT_SWITCH_POINT and (orientation_mask is not None or add_subway_walk):
            bytes_list = _bytes_from_values_str(values_str)
            rows = tsw.decode_switch_array(bytes_list)
            if orientation_mask is not None:
                rows = _apply_orientation_override(rows, orientation_mask)
            if add_subway_walk:
                rows = _ensure_subway_walk_pair(rows)
            output.append(_rewrite_tsec_line(virtual_dat, line, rows))
        elif prop_id == tsw.PROP_TRANSIT_SWITCH_ENTRY_COST and override_cost is not None:
            output.append(_rewrite_float_line(virtual_dat, prop_id, override_cost))
        elif prop_id == tsw.PROP_TRANSIT_SWITCH_TRAFFIC_CAPACITY and override_capacity is not None:
            output.append(_rewrite_float_line(virtual_dat, prop_id, override_capacity))
        else:
            output.append(line)
    return output


def _bytes_from_values_str(values_str: str) -> list[int]:
    """Parse the ``(0xa,0xb,...)`` body of a Uint8 array prop line."""
    out: list[int] = []
    for token in values_str.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(int(token, 0))
        except ValueError:
            logger.warning("Could not parse TSEC byte token %r", token)
    return out


def _through_network_for_lines(prop_lines: Iterable[str]) -> Optional[int]:
    """Look at the TSEC prop in a preset's emitted lines and return the
    through-network travel type (the one that self-pairs), or ``None`` for
    proximity-only presets.
    """
    for line in prop_lines:
        parsed = _parse_prop_line(line)
        if parsed is None or parsed[0] != tsw.PROP_TRANSIT_SWITCH_POINT:
            continue
        rows = tsw.decode_switch_array(_bytes_from_values_str(parsed[4]))
        return _find_through_travel(rows)
    return None


# --- The wizard dialog -----------------------------------------------------

ORIENTATION_CHOICES = (
    ("proximity", LEXTransitPresetOrientationProximity, tsw.EDGE_BITS_ALL),
    ("on_top_we", LEXTransitPresetOrientationOnTopWE, tsw.EDGE_BIT_WEST | tsw.EDGE_BIT_EAST),
    ("on_top_ns", LEXTransitPresetOrientationOnTopNS, tsw.EDGE_BIT_NORTH | tsw.EDGE_BIT_SOUTH),
)


class PresetWizardDialog(wx.Dialog):
    """Pick a preset, optionally rewrite the orientation/subway/capacity,
    preview the result, apply.
    """

    def __init__(self, parent: wx.Window, virtual_dat, exemplar, app_GID: int):
        wx.Dialog.__init__(
            self,
            parent,
            -1,
            LEXTransitPresetTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.virtual_dat = virtual_dat
        self.exemplar = exemplar
        self.app_GID = app_GID
        self._scope = build_eval_scope(virtual_dat, exemplar, app_GID)
        self._presets = list_transit_presets(virtual_dat)

        self.presetChoice = wx.Choice(self, -1, choices=self._preset_labels())
        if self._presets:
            self.presetChoice.SetSelection(0)

        self.orientationRadio = wx.RadioBox(
            self,
            -1,
            LEXTransitPresetOrientation,
            choices=[label for _key, label, _mask in ORIENTATION_CHOICES],
            majorDimension=3,
            style=wx.RA_SPECIFY_COLS,
        )
        self.alwaysSubwayCheck = wx.CheckBox(self, -1, LEXTransitPresetAlwaysSubway)

        # Cost & capacity: always-editable text fields prefilled with the
        # evaluated values. Whatever's in the field on Apply gets written.
        self.costText = wx.TextCtrl(self, -1, "")
        self.capacityText = wx.TextCtrl(self, -1, "")
        cost_label = self._prop_name(tsw.PROP_TRANSIT_SWITCH_ENTRY_COST)
        cap_label = self._prop_name(tsw.PROP_TRANSIT_SWITCH_TRAFFIC_CAPACITY)
        switches_label = self._prop_name(tsw.PROP_TRANSIT_SWITCH_POINT)

        # Switches preview: same columns and look as the TSEC editor.
        self.previewList = tsw.AutoWidthListCtrl(self)
        for idx, (label, width) in enumerate(
            [
                (LEXTransitSwitchColHex, 110),
                (LEXTransitSwitchColArt, 150),
                (LEXTransitSwitchColEdges, 150),
                (LEXTransitSwitchColFrom, 110),
                (LEXTransitSwitchColTo, 110),
            ]
        ):
            self.previewList.InsertColumn(idx, label, width=width)
        self.previewList.SetMinSize((680, 200))

        # Footer: just OccupantGroups, labeled with its catalogue name.
        self.occupantGroupsText = wx.StaticText(self, -1, "")

        self.statusText = wx.StaticText(self, -1, "")
        self.statusText.SetForegroundColour(wx.Colour(160, 0, 0))

        self.applyButton = wx.Button(self, wx.ID_OK, LEXTransitPresetApply)
        self.applyButton.SetDefault()
        cancelButton = wx.Button(self, wx.ID_CANCEL, LEXTransitPresetCancel)

        sizer = wx.BoxSizer(wx.VERTICAL)
        topGrid = wx.FlexGridSizer(0, 2, 4, 8)
        topGrid.AddGrowableCol(1, 1)
        topGrid.Add(wx.StaticText(self, -1, LEXTransitPresetPick), 0, wx.ALIGN_CENTER_VERTICAL)
        topGrid.Add(self.presetChoice, 1, wx.EXPAND)
        sizer.Add(topGrid, 0, wx.EXPAND | wx.ALL, 8)

        sizer.Add(self.orientationRadio, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self.alwaysSubwayCheck, 0, wx.EXPAND | wx.ALL, 8)

        overrideGrid = wx.FlexGridSizer(0, 2, 4, 8)
        overrideGrid.AddGrowableCol(1, 1)
        overrideGrid.Add(wx.StaticText(self, -1, cost_label), 0, wx.ALIGN_CENTER_VERTICAL)
        overrideGrid.Add(self.costText, 1, wx.EXPAND)
        overrideGrid.Add(wx.StaticText(self, -1, cap_label), 0, wx.ALIGN_CENTER_VERTICAL)
        overrideGrid.Add(self.capacityText, 1, wx.EXPAND)
        sizer.Add(overrideGrid, 0, wx.EXPAND | wx.ALL, 8)

        sizer.Add(wx.StaticText(self, -1, switches_label), 0, wx.LEFT | wx.TOP, 8)
        sizer.Add(self.previewList, 1, wx.EXPAND | wx.ALL, 8)
        sizer.Add(self.occupantGroupsText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self.statusText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(self.applyButton)
        btns.AddButton(cancelButton)
        btns.Realize()
        sizer.Add(btns, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(sizer)

        self.presetChoice.Bind(wx.EVT_CHOICE, self._on_changed)
        self.orientationRadio.Bind(wx.EVT_RADIOBOX, self._on_changed)
        self.alwaysSubwayCheck.Bind(wx.EVT_CHECKBOX, self._on_changed)
        self.costText.Bind(wx.EVT_TEXT, self._on_changed)
        self.capacityText.Bind(wx.EVT_TEXT, self._on_changed)
        self.Bind(wx.EVT_BUTTON, self._on_apply, id=wx.ID_OK)

        # Default to always-include-subway per MGB's mitigation.
        self.alwaysSubwayCheck.SetValue(True)

        self._appliedCount = 0
        self._refresh_preset_dependent()
        self._refresh_preview()

    # --- internals ---------------------------------------------------------

    def _preset_labels(self) -> list[str]:
        if not self._presets:
            return [LEXTransitPresetEmpty]
        labels: list[str] = []
        for category, preset in self._presets:
            parent_name = category.parent.Name if category.parent is not None else ""
            base = "%s — %s" % (parent_name, category.Name) if parent_name else category.Name
            # Suffix the preset name only when it isn't the default "Standard",
            # so the common case stays uncluttered.
            if preset.Name and preset.Name.lower() not in ("standard", "default"):
                labels.append("%s: %s" % (base, preset.Name))
            else:
                labels.append(base)
        return labels

    def _selected_preset(self):
        """Returns the selected preset's category-shaped object, or None."""
        if not self._presets:
            return None
        idx = self.presetChoice.GetSelection()
        if idx < 0 or idx >= len(self._presets):
            return None
        return self._presets[idx][1]

    def _selected_category(self):
        if not self._presets:
            return None
        idx = self.presetChoice.GetSelection()
        if idx < 0 or idx >= len(self._presets):
            return None
        return self._presets[idx][0]

    def _selected_orientation_mask(self) -> int:
        idx = max(0, self.orientationRadio.GetSelection())
        return ORIENTATION_CHOICES[idx][2]

    def _prop_name(self, prop_id: int) -> str:
        """Look up a property's display name from the new_properties.xml
        catalogue. Falls back to a hex literal if the catalogue isn't
        loaded yet (e.g. during early init).
        """
        try:
            return self.virtual_dat.properties[prop_id].Name
        except (KeyError, AttributeError):
            return "0x%08X" % prop_id

    def _field_float(self, text: wx.TextCtrl) -> Optional[float]:
        raw = text.GetValue().strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _generate_lines(self) -> Optional[list[str]]:
        """Run the preset+overrides pipeline. Sets the status line on error."""
        preset = self._selected_preset()
        if preset is None or self._scope is None:
            return None
        try:
            # Import here to break the circular-import risk: this module is
            # imported from SC4PIMApp at right-click menu setup time, and
            # SC4PIMApp itself owns ``build_category_props_for_preset``.
            from .SC4PIMApp import build_category_props_for_preset

            base_lines = build_category_props_for_preset(self.virtual_dat, self.exemplar, preset, self._scope)
        except Exception as e:
            logger.exception("Preset eval failed for %s", preset.Name)
            self.statusText.SetLabel(LEXTransitPresetEvalError % e)
            return None
        return apply_overrides(
            self.virtual_dat,
            base_lines,
            self._selected_orientation_mask(),
            self.alwaysSubwayCheck.GetValue(),
            self._field_float(self.costText),
            self._field_float(self.capacityText),
        )

    def _refresh_preview(self) -> None:
        if not self._presets:
            self.previewList.DeleteAllItems()
            self.occupantGroupsText.SetLabel(LEXTransitPresetEmpty)
            self.applyButton.Enable(False)
            return
        if self._scope is None:
            self.previewList.DeleteAllItems()
            self.occupantGroupsText.SetLabel(LEXTransitPresetNotApplicable)
            self.statusText.SetLabel(LEXTransitPresetNotApplicable)
            self.applyButton.Enable(False)
            return
        self.statusText.SetLabel("")
        lines = self._generate_lines()
        if lines is None:
            self.previewList.DeleteAllItems()
            self.occupantGroupsText.SetLabel("")
            self.applyButton.Enable(False)
            return
        self.applyButton.Enable(True)
        self._populate_preview(lines)

    def _populate_preview(self, prop_lines: Iterable[str]) -> None:
        rows: list[tsw.SwitchRow] = []
        occupant_groups_str = ""
        for line in prop_lines:
            parsed = _parse_prop_line(line)
            if parsed is None:
                continue
            prop_id, _name, _type, _count, values_str = parsed
            values_str = values_str.strip()
            if prop_id == tsw.PROP_TRANSIT_SWITCH_POINT:
                rows = tsw.decode_switch_array(_bytes_from_values_str(values_str))
            elif prop_id == 0xAA1DD396:
                occupant_groups_str = values_str

        self.previewList.DeleteAllItems()
        for row_idx, row in enumerate(rows):
            self.previewList.InsertItem(row_idx, tsw.row_hex(row))
            self.previewList.SetItem(row_idx, 1, tsw.art_label(row.art))
            self.previewList.SetItem(row_idx, 2, tsw.edge_label(row.edges))
            self.previewList.SetItem(row_idx, 3, tsw.travel_label(row.frm))
            self.previewList.SetItem(row_idx, 4, tsw.travel_label(row.to))
            if row.expert:
                self.previewList.SetItemTextColour(row_idx, wx.Colour(140, 80, 0))

        if occupant_groups_str:
            self.occupantGroupsText.SetLabel(
                LEXTransitPresetPropLine % (self._prop_name(0xAA1DD396), occupant_groups_str)
            )
        else:
            self.occupantGroupsText.SetLabel("")

    def _on_changed(self, event: wx.Event) -> None:
        if event.GetEventObject() is self.presetChoice:
            self._refresh_preset_dependent()
        self._refresh_preview()
        event.Skip()

    def _refresh_preset_dependent(self) -> None:
        """Re-seed the orientation default and the cost/capacity text fields
        from whatever this preset's category evaluates to.
        """
        preset = self._selected_preset()
        if preset is None or self._scope is None:
            self.costText.SetValue("")
            self.capacityText.SetValue("")
            return
        try:
            from .SC4PIMApp import build_category_props_for_preset

            base_lines = build_category_props_for_preset(self.virtual_dat, self.exemplar, preset, self._scope)
        except Exception:
            base_lines = []

        cost_str, cap_str = "", ""
        for line in base_lines:
            parsed = _parse_prop_line(line)
            if parsed is None:
                continue
            prop_id, _name, _type, _count, values_str = parsed
            if prop_id == tsw.PROP_TRANSIT_SWITCH_ENTRY_COST:
                cost_str = values_str.strip()
            elif prop_id == tsw.PROP_TRANSIT_SWITCH_TRAFFIC_CAPACITY:
                cap_str = values_str.strip()
        self.costText.SetValue(cost_str)
        self.capacityText.SetValue(cap_str)

        # Default the orientation radio to whatever edge mask the preset
        # itself uses for its through-traffic rows. For proximity-only
        # presets the orientation has no effect, so we just leave the
        # default selection alone.
        through = _through_network_for_lines(base_lines)
        if through is None:
            return
        preset_mask = self._dominant_through_mask(base_lines, through)
        for idx, (_key, _label, mask) in enumerate(ORIENTATION_CHOICES):
            if mask == preset_mask:
                self.orientationRadio.SetSelection(idx)
                break

    def _dominant_through_mask(self, prop_lines, through_travel: int) -> int:
        """Find the edge-mask byte the preset uses for its self-pair rows.

        Used to seed the orientation radio so the dialog opens on the
        preset's authored orientation rather than the first radio option.
        """
        for line in prop_lines:
            parsed = _parse_prop_line(line)
            if parsed is None or parsed[0] != tsw.PROP_TRANSIT_SWITCH_POINT:
                continue
            rows = tsw.decode_switch_array(_bytes_from_values_str(parsed[4]))
            for row in rows:
                if row.frm == through_travel and row.to == through_travel:
                    return row.edges
        return tsw.EDGE_BITS_ALL

    def _on_apply(self, event: wx.Event) -> None:
        preset = self._selected_preset()
        category = self._selected_category()
        lines = self._generate_lines()
        if preset is None or lines is None:
            return
        # Honour removeProperties from the category chain (walk up so a
        # parent-category removal applies too); the preset itself can also
        # contribute removals.
        seen: set = set()
        walker = preset
        while walker is not None:
            for prop_id in walker.removeProperties.keys():
                if prop_id not in seen:
                    seen.add(prop_id)
                    self.exemplar.RemoveProp(prop_id)
            walker = getattr(walker, "parent", None)
        written = 0
        for line in lines:
            if self.exemplar.AddTextProp(line):
                written += 1
        self.exemplar.modified = True
        self._appliedCount = written
        label = "%s — %s" % (category.Name, preset.Name) if category else preset.Name
        self.statusText.SetLabel(LEXTransitPresetApplied % (label, written))
        event.Skip()

    # --- public --------------------------------------------------------

    def GetAppliedCount(self) -> int:
        return self._appliedCount
