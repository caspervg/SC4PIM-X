# SC4PIM-X Python 3.11+ Modernization Guide

## Overview

This document describes the modernization of SC4PIM-X from Python 2.4 to Python 3.11+. The codebase has been fully updated to support modern Python while maintaining backward compatibility where possible.

## What Changed

### Python Version Requirements

- **Minimum Python Version**: 3.11
- **Tested Python Versions**: 3.11, 3.12, 3.13
- **Old Python Version**: 2.4 (no longer supported)

### Core Python Syntax Updates

All Python 2 syntax has been updated to Python 3:

- `print` statements → `print()` functions
- `xrange()` → `range()`
- Long integer literals (`123L`) → regular integers (`123`)
- `.iteritems()` → `.items()`
- `.iterkeys()` → `.keys()`
- `unicode()` → `str()`
- `execfile()` → `exec(open().read())`
- Integer division `/` → `//` where appropriate
- Bare `except:` → `except Exception:`

### Library Modernization

#### Image Processing: PIL → Pillow
```python
# Old (Python 2)
import Image
import ImageDraw

# New (Python 3)
from PIL import Image
from PIL import ImageDraw
```

**API Changes:**
- `Image.fromstring()` → `Image.frombytes()`
- `Image.tostring()` → `Image.tobytes()`

#### Numeric Arrays: Numeric → NumPy
```python
# Old (Python 2)
import Numeric

# New (Python 3)
import numpy
```

#### Binary I/O: cStringIO/StringIO → io
```python
# Old (Python 2)
import cStringIO
import StringIO

# New (Python 3)
import io
# Use io.BytesIO for binary data
```

#### Threading: thread → _thread
```python
# Old (Python 2)
import thread

# New (Python 3)
import _thread as thread
```

### Cross-Platform Improvements

#### Windows Registry Access (Optional)

Win32 API calls are now optional and wrapped in try-except blocks:

```python
try:
    import win32api
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
```

The application will:
- Use Windows registry on Windows when `pywin32` is installed
- Fall back gracefully on non-Windows platforms or when `pywin32` is unavailable
- Generate GID (Group ID) locally if registry access fails

#### Removed Dependencies

- `dircache` - Deprecated module, removed (functionality was unused)

### Deprecated Modules Removed

The following Python 2 header comments from the decompilation process have been removed:
- `# uncompyle6 version ...`
- `# Python bytecode 2.4 ...`
- `# Decompiled from: ...`

## Installation

### Prerequisites

- Python 3.11 or higher
- `uv` package manager (recommended) or `pip`

### Using uv (Recommended)

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd sc4pim-x-decompilation
   uv sync
   ```

3. **Run the application**:
   ```bash
   uv run python -m library.SC4PIMApp
   ```

### Using pip

1. **Create virtual environment**:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python -m library.SC4PIMApp
   ```

## Dependencies

### Required Dependencies

- **wxPython** (>=4.2.0) - GUI framework
- **Pillow** (>=10.0.0) - Image processing (replaces PIL)
- **NumPy** (>=1.24.0) - Numerical arrays (replaces Numeric)
- **PyOpenGL** (>=3.1.0) - OpenGL bindings for 3D rendering
- **PyOpenGL-accelerate** (>=3.1.0) - OpenGL performance improvements

### Platform-Specific Dependencies

- **pywin32** (>=306) - Windows registry access (Windows only, optional)

### Development Dependencies

- **black** (>=23.0.0) - Code formatter
- **ruff** (>=0.1.0) - Fast Python linter
- **mypy** (>=1.0.0) - Static type checker

## Known Issues and Limitations

### FSHConverter.pyd Binary Module

The `FSHConverter.pyd` binary module is a compiled Python 2 extension. It may need to be recompiled for Python 3.11+ on Windows platforms. If this module fails to load:

1. The application will still run but FSH texture conversion may not work
2. Consider recompiling the module from source for Python 3.11+
3. Or implement a pure Python FSH converter as an alternative

### Platform Support

- **Windows**: Fully supported with optional registry access
- **macOS**: Supported (without registry features)
- **Linux**: Supported (without registry features)

### Python 2 Settings Files

If you have existing `settings.ini` or `config.ini` files from Python 2:
- Most Python 2 code will still work in Python 3
- Update any print statements to use `print()` functions
- Update any `xrange` to `range`
- Update any long integers (`123L`) to regular integers (`123`)

## Testing Recommendations

Before using with production SC4 data:

1. **Test basic functionality**:
   ```bash
   python -m library.SC4PIMApp
   ```

2. **Verify library imports**:
   ```bash
   python -c "from library.SC4PIMApp import *"
   python -c "from library.SC4DatTools import *"
   ```

3. **Test with sample data**:
   - Load a small .dat file
   - View a building lot
   - Preview textures
   - Test 3D rendering

4. **Cross-platform testing**:
   - Test on your target platform (Windows/macOS/Linux)
   - Verify OpenGL rendering works
   - Check file path handling

## Migration from Python 2

If you're migrating from a Python 2.4 installation:

1. **Backup your data** - Always backup your SC4 plugins and saves
2. **Uninstall Python 2 version** (optional but recommended)
3. **Install Python 3.11+** from [python.org](https://www.python.org/downloads/)
4. **Install dependencies** using `uv` or `pip` (see Installation section)
5. **Test thoroughly** with non-critical data first

## Development

### Code Style

The project now follows modern Python conventions:
- Black code formatting (120 character line length)
- Ruff linting
- Type hints (gradually being added)

### Running Linters

```bash
# Format code
uv run black library/

# Lint code
uv run ruff check library/

# Type check
uv run mypy library/
```

## Contributing

When contributing to the modernized codebase:

1. Use Python 3.11+ syntax and idioms
2. Follow the existing code style (use Black for formatting)
3. Add type hints to new functions
4. Test on multiple platforms if possible
5. Update documentation for significant changes

## Support

For issues related to the modernization:
- Check this README first
- Review the Git commit history for specific changes
- Open an issue on GitHub with:
  - Python version
  - Operating system
  - Error messages
  - Steps to reproduce

## Changelog

### Version 2009.0.0 (Modernization Release)

**Python 3.11+ Migration:**
- ✅ All Python 2 syntax updated to Python 3
- ✅ All libraries modernized (PIL→Pillow, Numeric→NumPy)
- ✅ Cross-platform improvements (optional Win32 API)
- ✅ Modern package management with `uv`
- ✅ Type hints infrastructure (gradual adoption)
- ✅ Code quality tools (Black, Ruff, MyPy)

**Breaking Changes:**
- Python 2.4 no longer supported
- Minimum Python version: 3.11
- FSHConverter.pyd may need recompilation

**Non-Breaking Changes:**
- Existing .dat files remain compatible
- Lot editor functionality preserved
- 3D rendering capabilities maintained
- Windows registry features remain (but optional)

## License

See main README.md for license information.

## Acknowledgments

- Original SC4PIM-X developers
- Python community for excellent migration tools
- Contributors to Pillow, NumPy, wxPython, and PyOpenGL projects
