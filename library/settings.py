# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: settings.pyo
# Compiled at: 2008-03-17 10:21:32
ItemOrderForPloppable = 1
ItemOrderForElementary = 2
ItemOrderForHighSchool = 5
ItemOrderForLibrary = 3
ItemOrderForCollege = 7
ItemOrderForMuseum = 6
bAdvancedUser = False
try:
    execfile('settings.ini')
except IOError:
    pass

try:
    execfile('config.ini')
except IOError:
    pass
# okay decompiling settings.pyo
