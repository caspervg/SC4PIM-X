# sc4pim-x-decompilation

## Decompilation steps
- Unpack `library.zip` in the SC4PIM directory via a quick Python script (a typical ZIP extractor will not work), like this one:
```python
import zipfile

with zipfile.ZipFile('library.zip', 'r') as zip_ref:
    zip_ref.extractall('./library')
```
This will yield tons of files with the `.pyo` extension in the newly extracted `library` folder
- Install uncompyle6 (I did this from a Python 2.7 installation, but I'm not sure if that's necessary
- Run the following for any files that you think are useful to decompile
```bash
uncompyle6 XYZ.pyo > XYZ.py
```
Replace XYZ by whatever file you wish to decompile, such as `SC4PIMApp`

## Info
- As you can see in `library/settings.py`, SC4PIM executes whatever code is in `settings.ini`. So this makes it an interesting entry point to monkey patch new instructions into the code.
- As SC4PIM was written in Python 2.4, your code in settings.ini will also need to be compatible with Python 2.4. That's very limiting! For example, `json` wasn't even part of the standard library yet!
- Example: these extra lines of code in `settings.ini` will make the text "Hello from DependenciesDlg!!" be written to "test.txt" each time the dependencies dialog is opened
```python
from DependenciesDlg import *
old_init = DependenciesDlg.__init__
def new_init(self, *k, **kw):
    old_init(self, *k, **kw)
    f = open("test.txt", "wa")
    f.write("hello from DependenciesDlg!!")
    f.close()
DependenciesDlg.__init__ = new_init
```

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

The result is a self-contained folder in `dist/SC4PIMX/`. On Windows, zip it
for distribution:

```powershell
Compress-Archive -Path dist/SC4PIMX -DestinationPath SC4PIMX-windows.zip
```

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
