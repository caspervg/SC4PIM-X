"""Shared wxPython helpers for the vendored Tabler SVG icon set."""


from functools import lru_cache

import wx

from .paths import asset_path

DEFAULT_COLOUR = "#000000"
COMPACT_ICON_SIZE = 18
COMPACT_BUTTON_SIZE = (34, 30)


@lru_cache(maxsize=None)
def icon_bundle(name, size=COMPACT_ICON_SIZE, colour=DEFAULT_COLOUR):
    """Return a cached, DPI-aware bitmap bundle for a Tabler outline icon."""
    size = int(size)
    if size <= 0:
        raise ValueError("Icon size must be positive")
    try:
        colour_bytes = str(colour).encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Icon colour must be an ASCII SVG colour") from exc
    path = asset_path("vendor", "tabler-icons", "svg", str(name) + ".svg")
    svg = path.read_bytes().replace(b"currentColor", colour_bytes)
    bundle = wx.BitmapBundle.FromSVG(svg, wx.Size(size, size))
    if not bundle.IsOk():
        raise ValueError("Unable to load Tabler icon: %s" % path)
    return bundle


def icon_bitmap(name, size=COMPACT_ICON_SIZE, colour=DEFAULT_COLOUR, window=None):
    """Return a concrete bitmap, scaled for ``window`` when one is supplied."""
    bundle = icon_bundle(name, size, colour)
    if window is not None:
        return bundle.GetBitmapFor(window)
    return bundle.GetBitmap(wx.Size(int(size), int(size)))


def set_button_icon(button, name, size=16, colour=DEFAULT_COLOUR, position=wx.LEFT):
    """Add an icon to a normal text or toggle button and return the button."""
    button.SetBitmap(icon_bundle(name, size, colour), position)
    try:
        button.SetBitmapMargins(4, 0)
    except AttributeError:
        pass
    return button


def icon_button(parent, name, tooltip="", icon_size=COMPACT_ICON_SIZE,
                button_size=COMPACT_BUTTON_SIZE, window_id=wx.ID_ANY):
    """Create a compact icon-only push button."""
    button = wx.BitmapButton(
        parent, window_id, icon_bundle(name, icon_size), size=button_size,
    )
    if tooltip:
        button.SetToolTip(tooltip)
    return button


def icon_toggle_button(parent, name, tooltip="", icon_size=COMPACT_ICON_SIZE,
                       button_size=COMPACT_BUTTON_SIZE, window_id=wx.ID_ANY):
    """Create a compact icon-only toggle button."""
    button = wx.BitmapToggleButton(
        parent, window_id, icon_bundle(name, icon_size), size=button_size,
    )
    if tooltip:
        button.SetToolTip(tooltip)
    return button
