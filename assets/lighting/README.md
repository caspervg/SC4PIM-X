# SC4 lighting profiles

Each subdirectory is a self-contained lighting profile with:

- `profile.toml`: package provenance and exemplar-derived settings.
- `global_light_map_0917660E.png`: the 32x32 time/month colour map from DBPF
  entry `856DDBAC-A9179251-0917660E`.
- `environment_shape_map_0917660C.png`: the 64x64 environment lookup geometry
  from entry `856DDBAC-A9179251-0917660C`.
- `environment_color_map_0917660D.png`: the paired 64x64 environment colours
  from entry `856DDBAC-A9179251-0917660D`.

`cSC4LightingManager` samples the map by normalized time of day (X) and month
(Y). The sampled red channel is also compared with `night_threshold` to drive
the graphical day/night state. This is separate from the Main Simulator's
wrapped night clock stored under `[clock]`.

The Mac `cSC4LightingManager::GetModelColor` path uses 0917660C for the lookup
dimensions and reads the resulting RGB pixel from 0917660D. SimFox replaces
0917660D but not 0917660C, so its profile contains an exact copy of the
inherited Maxis 0917660C alongside its own effective colour map.

Available profiles:

- `maxis/`: vanilla Rush Hour lighting.
- `simfox/`: SimFox Day 'n' Nite / DarkNite lighting. SimFox does not override
  the Main Simulator clock, so its profile records the inherited Maxis window.

A `gizmo/` profile can be added later using the same layout.

Keep the PNGs unmodified: their exact RGB pixels are simulation inputs, not
display artwork.
