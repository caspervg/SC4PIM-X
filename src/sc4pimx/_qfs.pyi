"""Type stub for the optional native QFS accelerator (sc4pimx._qfs).

The runtime module is a compiled C extension built by hatch_build.py; this stub
mirrors its public API so the pure-Python fallback in QFS.py type-checks against
it whether or not the .pyd is present.
"""

def decode(buffer: bytes) -> bytes | None: ...
def encode(buffer: bytes) -> bytes | None: ...
