# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: FSHConverter.pyo
# Compiled at: 2010-09-08 20:34:16


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
# okay decompiling FSHConverter.pyo
