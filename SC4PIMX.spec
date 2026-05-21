# -*- mode: python ; coding: utf-8 -*-
import os as _os, re as _re, sys as _sys

_ver = _re.search(r'VERSION = "([^"]+)"', open('src/sc4pimx/version.py').read()).group(1)
_ver_m = _re.match(r'(\d+)\.(\d+)', _ver)
_ver_tuple = (int(_ver_m.group(1)), int(_ver_m.group(2)), 0, 0) if _ver_m else (0, 0, 0, 0)

_win_ver_file = None
if _sys.platform == 'win32':
    _os.makedirs('build', exist_ok=True)
    _win_ver_file = 'build/version_info.txt'
    open(_win_ver_file, 'w').write(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={_ver_tuple},
    prodvers={_ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', ''),
         StringStruct('FileDescription', 'SC4PIM-X'),
         StringStruct('FileVersion', '{_ver}'),
         StringStruct('InternalName', 'SC4PIMX'),
         StringStruct('LegalCopyright', ''),
         StringStruct('OriginalFilename', 'SC4PIMX.exe'),
         StringStruct('ProductName', 'SC4PIM-X'),
         StringStruct('ProductVersion', '{_ver}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""")

# Bundled data: the assets/ tree (icons, backgrounds, dbpf/cohorts.dat,
# templates, plus the factory config.toml and new_properties.xml).
datas = [
    ('assets', 'assets'),
]

# PyOpenGL loads its platform and array backends dynamically; PyInstaller
# cannot see those imports statically, so list them explicitly.
hiddenimports = [
    'OpenGL.arrays.ctypesarrays',
    'OpenGL.arrays.ctypesparameters',
    'OpenGL.arrays.ctypespointers',
    'OpenGL.arrays.lists',
    'OpenGL.arrays.nones',
    'OpenGL.arrays.numbers',
    'OpenGL.arrays.numpymodule',
    'OpenGL.arrays.strings',
    'OpenGL_accelerate',
]
if _sys.platform == 'win32':
    hiddenimports.append('OpenGL.platform.win32')
elif _sys.platform == 'darwin':
    hiddenimports.append('OpenGL.platform.darwin')
else:
    hiddenimports.append('OpenGL.platform.glx')


def _drop_obsolete_opengl_vc9_dlls(toc):
    """Drop PyOpenGL DLLs for unsupported pre-Python-3.5 Windows runtimes."""
    if _sys.platform != 'win32':
        return toc
    filtered = []
    for entry in toc:
        dest = entry[0].replace('\\', '/').lower()
        name = dest.rsplit('/', 1)[-1]
        if dest.startswith('OpenGL/DLLS/'.lower()) and name.endswith('.vc9.dll'):
            continue
        filtered.append(entry)
    return filtered

a = Analysis(
    ['scripts/run_sc4pimx.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
a.binaries = _drop_obsolete_opengl_vc9_dlls(a.binaries)
a.datas = _drop_obsolete_opengl_vc9_dlls(a.datas)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SC4PIMX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_win_ver_file,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SC4PIMX',
)
if _sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='SC4PIMX.app',
        bundle_identifier='com.caspervg.sc4pimx',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': _ver,
        },
    )
