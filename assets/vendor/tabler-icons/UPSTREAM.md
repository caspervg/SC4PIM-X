# Tabler Icons

- Version: 3.44.0
- Upstream: https://github.com/tabler/tabler-icons
- Release tag: v3.44.0
- Archive: `tabler-icons-3.44.0.zip`
- Archive SHA-256: `92E47C4E508C0813A16F0597DCD989F4BC1A7980695380A8EADC50C2A610EAB3`
- Vendored: 2026-07-05
- License: MIT; see `LICENSE`

Only the outline SVGs used by SC4PIM-X are included. Upstream filenames are
retained so the selection can be refreshed mechanically from a future Tabler
Icons release.

## Lot Editor Mapping

| Action | SVG |
| --- | --- |
| Pan mode | `hand-move.svg` |
| Prop mode | `cube.svg` |
| Base texture mode | `texture.svg` |
| Overlay texture mode | `layers-intersect.svg` |
| Flora mode | `trees.svg` |
| Transit mode | `route.svg` |
| Constraint mode | `droplet-half-2.svg` |
| Duplicate | `copy.svg` |
| Delete | `trash.svg` |
| Cycle 2D/3D view | `cube-3d-sphere.svg` |
| Zoom out | `zoom-out.svg` |
| Zoom in | `zoom-in.svg` |
| Fit view | `focus-centered.svg` |
| Snap grid | `grid-dots.svg` |
| Lot icon preview | `photo.svg` |
| Layer menu | `layers-selected.svg` |
| Align left | `layout-align-left.svg` |
| Align right | `layout-align-right.svg` |
| Align horizontal center | `layout-align-center.svg` |
| Align top | `layout-align-top.svg` |
| Align bottom | `layout-align-bottom.svg` |
| Align vertical center | `layout-align-middle.svg` |
| Rotate left | `rotate-2.svg` |
| Rotate right | `rotate-clockwise-2.svg` |
| Mirror | `flip-horizontal.svg` |
| Undo | `arrow-back-up.svg` |
| Redo | `arrow-forward-up.svg` |

## Shared UI Mapping

| Action | SVG |
| --- | --- |
| Add | `plus.svg` |
| Edit | `pencil.svg` |
| Move up/down | `arrow-up.svg`, `arrow-down.svg` |
| Sort | `sort-ascending.svg`, `sort-descending.svg`* |
| Play/pause | `player-play.svg`, `player-pause.svg` |
| Apply preset | `wand.svg` |
| Grid/list view | `layout-grid.svg`, `list.svg` |
| Current lot/library/favorites | `building-community.svg`, `library.svg`, `star.svg` |
| Save/close | `device-floppy.svg`, `x.svg` |
| Expand/collapse tree | `fold-down.svg`, `fold-up.svg` |
| Clear route | `route-off.svg` |
| Package lookup/running | `packages.svg`, `loader-2.svg` |
| Browse | `folder-open.svg` |
| Select/deselect all | `select-all.svg`, `deselect.svg` |
| Confirm/apply | `check.svg`, `checks.svg` |
| Pin/unpin | `pin.svg`, `pinned.svg` |
| Status | `circle-check.svg`, `alert-triangle.svg`, `info-circle.svg` |
| Neutral trend | `minus.svg` |

\* `sort-descending.svg` is a hand-authored placeholder (a vertical mirror of
`sort-ascending.svg`), not pulled from the pinned v3.44.0 release — it could
not be fetched from `github.com/tabler/tabler-icons` or an npm mirror in the
environment this was authored in. Replace it with the real upstream file when
possible, e.g. via `packages/icons/icons/outline/sort-descending.svg` in the
tagged release archive.
