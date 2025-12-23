"""FSH Converter module loader for SC4PIM.

This module dynamically loads the FSHConverter.pyd binary extension.
Note: This binary module may need to be recompiled for Python 3.11+.
"""


def __load():
    import imp
    import os
    import sys
    try:
        dirname = os.path.dirname(__loader__.archive)
    except NameError:
        dirname = sys.prefix

    path = os.path.join(dirname, 'FSHConverter.pyd')
    mod = imp.load_dynamic(__name__, path)


__load()
del __load
