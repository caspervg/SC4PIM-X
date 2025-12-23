"""User settings and configuration loader for SC4PIM."""
ItemOrderForPloppable = 1
ItemOrderForElementary = 2
ItemOrderForHighSchool = 5
ItemOrderForLibrary = 3
ItemOrderForCollege = 7
ItemOrderForMuseum = 6
bAdvancedUser = False
try:
    with open('settings.ini') as f:
        exec(f.read())
except IOError:
    pass

try:
    with open('config.ini') as f:
        exec(f.read())
except IOError:
    pass
