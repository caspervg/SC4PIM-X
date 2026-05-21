"""PyInstaller hook for PyOpenGL with unsupported VC9 DLLs filtered out."""

from pathlib import Path

from PyInstaller.compat import is_darwin, is_win
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

if is_win:
    hiddenimports = ['OpenGL.platform.win32']
elif is_darwin:
    hiddenimports = ['OpenGL.platform.darwin']
else:
    hiddenimports = ['OpenGL.platform.glx']

hiddenimports += collect_submodules('OpenGL.arrays')

datas = []
if is_win:
    # PyOpenGL ships DLLs for old Python/MSVC runtimes as well as current ones.
    # This project requires Python 3.11+, whose PyOpenGL loader selects vc14.
    datas = [
        item
        for item in collect_data_files('OpenGL')
        if not Path(item[0]).name.lower().endswith('.vc9.dll')
    ]
