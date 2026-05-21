"""User settings for SC4PIM.

The values are loaded from config.toml (see :mod:`sc4pimx.config`) and exposed
as module-level names so the category eval formulas in new_properties.xml can
reference them directly via ``from .settings import *``.
"""
from .config import load_settings

# Defaults; overridden by config.toml when present.
ItemOrderForPloppable = 1
ItemOrderForElementary = 2
ItemOrderForHighSchool = 5
ItemOrderForLibrary = 3
ItemOrderForCollege = 7
ItemOrderForMuseum = 6
bAdvancedUser = True

globals().update(load_settings())
