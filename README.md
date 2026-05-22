# SC4PIM-X

SC4PIM-X — also known as PIM-X, X-PIM or X-Tool — is a plugin manager and lot
editor for **SimCity 4**: "a better Maxis PIM and Maxis Lot Editor". It builds
building, prop, flora and foundation exemplars from SC4 models, creates and
edits growable and ploppable lots, manages building/prop families, lists lot
dependencies, and includes a 2D/3D lot editor with grid snapping.

This repository is a **decompilation and Python 3 modernization** of the
original SC4PIM-X. The original was written in Python 2.4 by **wouanagaine** in 2009
and distributed only as compiled bytecode; it has since been kept alive by the
SimCity 4 community. This is an unofficial preservation and continuation
project — it is **not affiliated with EA/Maxis or the original author**.

> The decompilation and modernization were carried out primarily using
> GitHub Copilot and Claude Code, supervised and verified by a human maintainer.

## Running from source

Install [uv](https://docs.astral.sh/uv/), then:

```sh
uv sync
uv run sc4pimx
```

## Building a standalone executable

SC4PIM-X ships a [PyInstaller](https://pyinstaller.org/) spec
(`SC4PIMX.spec`):

```sh
uv sync --group build
uv run pyinstaller --clean --noconfirm SC4PIMX.spec
```

The result is a self-contained folder in `dist/SC4PIMX/` (`SC4PIMX.exe` plus an
`_internal/` folder — distribute the whole folder, not just the exe). On
Windows, zip it for distribution:

```powershell
Compress-Archive -Path dist/SC4PIMX -DestinationPath SC4PIMX-windows.zip
```

Tagged releases (`vYYYY.Na`, e.g. `v2026.1a`) are built automatically for
Windows and macOS by GitHub Actions and published as a GitHub Release.

## User data location

Per-user state lives in `%APPDATA%\sc4pimx\` (Windows) — this includes
`config.toml`, `groups.ini`, `sc4pimx.log`, `faulthandler.log`, and the
`ImageDB` / `ImageDBLarge` thumbnail caches. The factory `config.toml`,
`new_properties.xml`, and the language files in `lang/` ship in `assets/`;
dropping your own copy of any of them into `%APPDATA%\sc4pimx\` (e.g.
`%APPDATA%\sc4pimx\lang\fr.toml`) overrides the bundled one.

## Logging

Logging is configured from the `[Logging]` table in `config.toml`. Set
`Level = "DEBUG"` to include verbose startup and loading timing messages.
Logs rotate by default at `%APPDATA%\sc4pimx\sc4pimx.log`.

## Translations

UI strings live in `assets/lang/<code>.toml`, with `en.toml` as the base
language. To add a language, copy `en.toml` to e.g. `fr.toml`, translate the
values, and set `Language = "fr"` in `config.toml`. Missing keys fall back to
English, so partial translations are fine.

## License

No formal license has been granted for SC4PIM-X. The original was created by
wouanagaine, who never published its source or attached a license — the source
was lost and the tool became unmaintainable. Copyright in the original work
remains with the original author, and all rights are reserved.

This repository is a good-faith community preservation and modernization
effort, provided as-is with no warranty. See the [`NOTICE`](NOTICE) file for
the full provenance statement and takedown contact.

## Provenance

The original SC4PIM-X was recovered by decompiling its `library.zip`:

1. Unpack `library.zip` from the SC4PIM directory with a short Python script
   (a normal ZIP extractor will not work):
   ```python
   import zipfile
   with zipfile.ZipFile('library.zip', 'r') as zip_ref:
       zip_ref.extractall('./library')
   ```
   This yields many `.pyo` files in the `library` folder.
2. Decompile the useful ones with [uncompyle6](https://github.com/rocky/python-uncompyle6):
   ```sh
   uncompyle6 SC4PIMApp.pyo > SC4PIMApp.py
   ```

The recovered Python 2.4 sources were then modernized to Python 3.11+ and a number of performance and QoL improvements were made.
The original decompilation is preserved in the `archive/decompiled-py24` branch and tag.
