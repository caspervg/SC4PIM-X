"""Hatchling build hook that compiles the optional native QFS accelerator.

The accelerator (``sc4pimx._qfs``) is strictly optional: ``sc4pimx.QFS`` falls
back to its pure-Python codec when the extension is absent.  So this hook is
deliberately best-effort -- it compiles the ``.pyd`` when an MSVC toolchain is
available on Windows and otherwise prints a note and lets the build proceed.

It is Windows-only by design (SimCity 4, and thus this app, is Windows-only).
The extension is built against the CPython limited API (abi3), so a single
``_qfs.pyd`` is valid across the supported 3.11-3.13 range.

Run standalone to (re)build in place for a dev checkout:

    uv run python hatch_build.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from pathlib import Path

_PACKAGE_DIR = Path("src") / "sc4pimx"
_SOURCE = _PACKAGE_DIR / "_qfsmodule.c"
_OUTPUT = _PACKAGE_DIR / "_qfs.pyd"  # abi3 name; CPython accepts a bare .pyd


def _find_vcvars() -> str | None:
    """Locate ``vcvars64.bat`` via vswhere, then a few well-known fallbacks."""

    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if vswhere.is_file():
        try:
            result = subprocess.run(
                [str(vswhere), "-latest", "-products", "*", "-property", "installationPath"],
                capture_output=True,
                text=True,
                check=False,
            )
            install_path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            if install_path:
                vcvars = Path(install_path) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
                if vcvars.is_file():
                    return str(vcvars)
        except (OSError, IndexError):
            pass

    for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), program_files_x86):
        base = Path(root) / "Microsoft Visual Studio"
        if not base.is_dir():
            continue
        for vcvars in sorted(base.glob("*/*/VC/Auxiliary/Build/vcvars64.bat"), reverse=True):
            if vcvars.is_file():
                return str(vcvars)
    return None


def compile_extension(log=print) -> bool:
    """Compile ``_qfsmodule.c`` -> ``_qfs.pyd`` in place. Return True on success."""

    if sys.platform != "win32":
        log("[qfs-accel] non-Windows platform; skipping native accelerator (pure-Python fallback).")
        return False

    if not _SOURCE.is_file():
        log(f"[qfs-accel] source {_SOURCE} not found; skipping.")
        return False

    # Rebuild if either the C source or this build script (which holds the
    # compiler flags) is newer than the artifact.
    newest_input = max(_SOURCE.stat().st_mtime, Path(__file__).stat().st_mtime)
    if _OUTPUT.is_file() and _OUTPUT.stat().st_mtime >= newest_input:
        log(f"[qfs-accel] {_OUTPUT} is up to date.")
        return True

    vcvars = _find_vcvars()
    if not vcvars:
        log("[qfs-accel] no MSVC toolchain found; skipping native accelerator (pure-Python fallback).")
        return False

    paths = sysconfig.get_paths()
    include = paths["include"]
    platinclude = paths.get("platinclude", include)
    libs = os.path.join(sys.base_prefix, "libs")

    # Run through a temp .bat: cmd's /c quote handling mangles a command string
    # that both starts with a quoted path and uses &&, so a script file is the
    # robust way to chain vcvars + cl.  Output names are relative to cwd (the
    # package dir) to avoid quoting paths with spaces on the command line.
    # Maximum portable optimization (no /arch:AVX2 etc. -- the .pyd ships to
    # arbitrary CPUs): /O2 max speed, /Ob3 aggressive inlining, /GL+/LTCG whole-
    # program optimization, /Gy+/Gw + /OPT:REF,ICF fold dead code/data.
    # /LD build DLL, link the limited-API import lib (abi3).
    cflags = "/nologo /O2 /Ob3 /Oi /Ot /GL /Gy /Gw /DNDEBUG /W3 /LD"
    ldflags = "/LTCG /OPT:REF /OPT:ICF"
    script = (
        "@echo off\n"
        f'call "{vcvars}" >nul\n'
        f'cl {cflags} "{_SOURCE.name}" '
        f'/I"{include}" /I"{platinclude}" '
        f'/Fo"_qfs.obj" /Fe"_qfs.pyd" '
        f'/link {ldflags} /LIBPATH:"{libs}" python3.lib\n'
    )
    bat = (_PACKAGE_DIR / "_build_qfs.bat").resolve()
    try:
        bat.write_text(script, encoding="ascii")
        result = subprocess.run(
            ["cmd", "/c", str(bat)],
            cwd=str(_PACKAGE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        log(f"[qfs-accel] compiler invocation failed ({exc}); using pure-Python fallback.")
        return False
    finally:
        try:
            bat.unlink()
        except OSError:
            pass

    if result.returncode != 0 or not _OUTPUT.is_file():
        log("[qfs-accel] compilation failed; using pure-Python fallback. Compiler output:")
        log(result.stdout)
        log(result.stderr)
        return False

    # Tidy intermediate artifacts (best effort).
    for junk in ("_qfs.obj", "_qfs.lib", "_qfs.exp"):
        try:
            (_PACKAGE_DIR / junk).unlink()
        except OSError:
            pass

    log(f"[qfs-accel] built {_OUTPUT}.")
    return True


# hatchling is only present in the build environment, not the runtime venv, so
# defer importing it.  Running this file standalone (the dev rebuild path) just
# needs compile_extension and must not require hatchling.
try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface  # type: ignore[import-not-found]
except ImportError:
    BuildHookInterface = object  # type: ignore[assignment,misc]


class QFSAcceleratorBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name not in ("wheel", "editable"):
            return
        if compile_extension(log=self.app.display_info) and _OUTPUT.is_file():
            # Ship the compiled artifact in the wheel.
            build_data.setdefault("force_include", {})[str(_OUTPUT)] = "sc4pimx/_qfs.pyd"
            build_data["pure_python"] = False
            build_data["infer_tag"] = True


if __name__ == "__main__":
    ok = compile_extension()
    sys.exit(0 if ok else 1)
