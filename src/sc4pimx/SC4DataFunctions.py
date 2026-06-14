import functools
import logging
import struct

from .translation import categoryLocalized
from .util import DictWrapper, basic_cmp

logger = logging.getLogger(__name__)


# Exemplar property 0x49C9C93C — "Nighttime State Change" (Uint8). When
# non-zero, the prop renders its state-N model variant at night instead of
# state 0.
NIGHTTIME_STATE_CHANGE_PROP = 0x49C9C93C
MODEL_IS_PRELIT_PROP = 0x6A845768


def night_state_for(exemplar):
    """Return the model state to display under night lighting for *exemplar*.

    Reads exemplar property 0x49C9C93C ("Nighttime State Change"). Returns 0
    when the property is missing, zero, or unreadable — in which case the
    daytime state is used unchanged.
    """
    if exemplar is None:
        return 0
    try:
        val = exemplar.GetProp(NIGHTTIME_STATE_CHANGE_PROP)
    except Exception:
        return 0
    if not val:
        return 0
    try:
        return int(val[0])
    except (TypeError, ValueError, IndexError):
        return 0


def model_is_prelit(exemplar):
    """Return whether *exemplar* disables game lighting for its model."""
    if exemplar is None:
        return False
    try:
        val = exemplar.GetProp(MODEL_IS_PRELIT_PROP)
    except Exception:
        return False
    if not val:
        return False
    try:
        return bool(int(val[0]))
    except (TypeError, ValueError, IndexError):
        return True


def ReadStageVsDensity(node):
    purpose = str(node.getAttribute("purpose"))
    wealth = int(node.getAttribute("wealth"))
    ratio = [float(x) for x in str(node.getAttribute("ratio")).split(",")]
    baseTex = int(node.getAttribute("baseTex"), 16)
    return (ratio, purpose, wealth, baseTex)


def ReadZoning(node):
    purpose = str(node.getAttribute("purpose"))
    value = int(node.getAttribute("value"))
    stages = [int(x) for x in str(node.getAttribute("stages")).split(",")]
    height = int(node.getAttribute("height"))
    return (purpose, value, stages, height)


def readPropertyDef(node):
    prop = DictWrapper({})
    prop.Name = str(node.getAttribute("Name"))
    id = node.getAttribute("ID").upper()
    if id[:2] == "0X":
        prop.ID = int(node.getAttribute("ID"), 16)
    else:
        prop.ID = node.getAttribute("ID").upper()
    prop.Type = str(node.getAttribute("Type"))
    count = node.getAttribute("Count").upper()
    if count == "":
        count = "1"
    prop.Count = int(count)
    if node.getAttribute("ShowAsHex").upper() == "Y":
        prop.ShowAsHex = True
    else:
        prop.ShowAsHex = False
    options = {}
    option_groups = {}
    current_option_group = ""
    prop.ShowAsMap = False
    minVal = node.getAttribute("MinValue")
    maxVal = node.getAttribute("MaxValue")
    if minVal is None or minVal == "":
        if prop.Type == "Uint32" or prop.Type == "Uint8":
            minVal = 0
        if prop.Type == "Sint32" or prop.Type == "Sint64":
            minVal = -100000000
        if prop.Type == "Float32":
            minVal = -100000000.0
    else:
        if len(minVal) > 1 and minVal[1] == "x":
            minVal = int(minVal, 16)
        else:
            minVal = int(minVal)
        if maxVal is None or maxVal == "":
            if prop.Type == "Uint32":
                maxVal = 4294967295
            if prop.Type == "Uint8":
                maxVal = 255
            if prop.Type == "Sint32":
                maxVal = 2147483647
            if prop.Type == "Sint64":
                maxVal = 9223372036854775807
            if prop.Type == "Float32":
                maxVal = 100000000.0
        elif len(maxVal) > 1 and maxVal[1] == "x":
            maxVal = int(maxVal, 16)
        else:
            maxVal = int(maxVal)
        prop.maxVal = maxVal
        prop.minVal = minVal
    # OPTION/FORMAT children must be read for every property, not only those
    # that declare a MinValue. Properties such as OccupantGroups list named
    # options but have no numeric range; nesting this loop inside the
    # MinValue branch dropped their option labels entirely.
    for subNode in node.childNodes:
        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == "FORMAT":
            prop.ShowAsMap = True
        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == "HELP":
            help_text = getText(subNode.childNodes).strip()
            if help_text.startswith("SubMenuROOT"):
                current_option_group = help_text
        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == "OPTION":
            value = subNode.getAttribute("Value").upper()
            if value[:3] == "COL":
                pass
            elif len(value) > 2 and value[1] == "X":
                value = int("0x" + value[2:], 16)
            else:
                value = int(value)
            meaning = subNode.getAttribute("Name")
            options[value] = meaning
            if current_option_group:
                option_groups[value] = current_option_group

    prop.Options = options
    prop.OptionGroups = option_groups
    return prop


def ToUnsigned(val):
    # Reinterpret as a 32-bit unsigned int. Callers pass float results of
    # coordinate maths (coerce to int) and signed differences that can fall
    # outside the 32-bit range; Python 2's struct masked the overflow, so
    # mask explicitly here instead of letting struct.pack raise.
    return int(val) & 0xFFFFFFFF


def ToTile(val):
    # Reinterpret the 32-bit value as signed. The input may be a signed
    # difference of raw coordinates (e.g. values[6] - centre), so mask into
    # the unsigned range before packing, matching Python 2 overflow masking.
    try:
        masked = int(val) & 0xFFFFFFFF
        return float(struct.unpack("<i", struct.pack("<I", masked))[0]) / float(1048576)
    except Exception:
        logger.exception("Failed to convert value to tile coordinate: %r (%s)", val, type(val).__name__)
        raise


def ToCoord(val):
    return ToTile(val) * 16.0


def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data

    return rc


def _init_props_container(obj):
    """Attach the empty prop-collection dicts every category / preset needs."""
    obj.code = []
    obj.setProperties = DictWrapper({})
    obj.factorProperties = DictWrapper({})
    obj.pairedFactorProperties = DictWrapper({})
    obj.programProperties = DictWrapper({})
    obj.evalProperties = DictWrapper({})
    obj.removeProperties = DictWrapper({})


def _parse_properties_block(properties_node, target):
    """Read a ``<PROPERTIES>`` element into a category-shaped target object.

    Shared by ``<CATEGORY>`` and its child ``<PRESET>`` elements so both go
    through the existing prop-generation pipeline unchanged.
    """
    for subsubNode in properties_node.childNodes:
        if subsubNode.nodeType != properties_node.ELEMENT_NODE:
            continue
        if subsubNode.tagName == "eval":
            name = subsubNode.getAttribute("name")
            expr = subsubNode.getAttribute("value")
            target.code.append((name, expr))
            continue
        if subsubNode.tagName != "PROPERTY":
            continue
        id = subsubNode.getAttribute("ID").upper()
        if id[:2] == "0X":
            id = int(id.lower(), 16)
        else:
            id = int(id)
        removep = subsubNode.getAttribute("Remove")
        if removep:
            target.removeProperties[id] = removep
        value = subsubNode.getAttribute("Value")
        if value:
            target.setProperties[id] = value
        factor = subsubNode.getAttribute("Factor")
        if factor:
            target.factorProperties[id] = [float(f) for f in factor.split(",")]
        pairedFactor = subsubNode.getAttribute("PairedFactor")
        if pairedFactor:
            paired = pairedFactor.split(",")
            target.pairedFactorProperties[id] = []
            for i in range(len(paired) // 2):
                target.pairedFactorProperties[id].append((paired[i * 2], float(paired[i * 2 + 1])))
        setVal = subsubNode.getAttribute("Set")
        if setVal:
            target.programProperties[id] = setVal
        evalVal = subsubNode.getAttribute("Eval")
        if evalVal:
            target.evalProperties[id] = evalVal


def readCategoryDef(node):
    cat = DictWrapper({})
    cat.descriptors = []
    cat.parent = None
    cat.imgName = None
    cat.imgIdx = None
    cat.imgName = node.getAttribute("img")
    cat.Name = node.getAttribute("Name")
    id = node.getAttribute("ID").upper()
    if id[:2] == "0X":
        cat.ID = int(node.getAttribute("ID"), 16)
    else:
        cat.ID = node.getAttribute("ID").upper()
    parentID = node.getAttribute("ParentID").upper()
    if parentID[:2] == "0X":
        cat.parentID = int(node.getAttribute("ParentID"), 16)
    else:
        cat.parentID = node.getAttribute("ParentID").upper()
    if cat.ID in categoryLocalized:
        cat.Name = categoryLocalized[cat.ID]
    cat.childs = []
    cat.filters = DictWrapper({})
    cat.filters.needed = []
    cat.filters.notallowed = []
    _init_props_container(cat)
    # ``<PRESET>`` children of a CATEGORY: each becomes a category-shaped
    # sub-object whose .parent is this CATEGORY, so the existing prop
    # pipeline walks up into the category for defaults / eval aliases.
    cat.presets = []
    for subNode in node.childNodes:
        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == "PROPERTIES":
            _parse_properties_block(subNode, cat)
        elif subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == "PRESET":
            preset = DictWrapper({})
            preset.Name = subNode.getAttribute("Name") or "Default"
            preset.Type = subNode.getAttribute("Type").strip()
            # Synthesise an ID so debug logs and any future de-dup behave.
            preset.ID = "%s::%s" % (cat.ID, preset.Name)
            preset.parent = cat
            preset.childs = []
            preset.descriptors = []
            preset.filters = DictWrapper({})
            preset.filters.needed = []
            preset.filters.notallowed = []
            _init_props_container(preset)
            for ppNode in subNode.childNodes:
                if ppNode.nodeType == node.ELEMENT_NODE and ppNode.tagName == "PROPERTIES":
                    _parse_properties_block(ppNode, preset)
            cat.presets.append(preset)

        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == "FILTERS":
            for subsubNode in subNode.childNodes:
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == "NEEDED":
                    id = subsubNode.getAttribute("ID").upper()
                    if id[:2] == "0X":
                        id = int(id.lower(), 16)
                    else:
                        id = int(id)
                    value = subsubNode.getAttribute("Value")
                    if value == "":
                        value = None
                    if value:
                        value = value.upper()
                        if value[:2] == "0X":
                            value = int(value.lower(), 16)
                        else:
                            value = int(value)
                    cat.filters.needed.append((id, value))
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == "NOT":
                    id = subsubNode.getAttribute("ID").upper()
                    if id[:2] == "0X":
                        id = int(id.lower(), 16)
                    else:
                        id = int(id)
                    value = subsubNode.getAttribute("Value")
                    if value == "":
                        value = None
                    if value:
                        value = value.upper()
                        if value[:2] == "0X":
                            value = int(value.lower(), 16)
                        else:
                            value = int(value)
                    cat.filters.notallowed.append((id, value))

    return cat


def DuplicateProp(dup, new_instance_id):
    prop = DictWrapper({})
    prop.Name = dup.Name
    prop.ID = new_instance_id
    prop.Type = dup.Type
    prop.Count = dup.Count
    prop.ShowAsHex = dup.ShowAsHex
    prop.ShowAsMap = dup.ShowAsMap
    prop.maxVal = dup.maxVal if hasattr(dup, "maxVal") else None
    prop.minVal = dup.minVal if hasattr(dup, "minVal") else None
    prop.Options = dup.Options
    prop.OptionGroups = getattr(dup, "OptionGroups", {})
    return prop


def FinalizeCategory(root):
    root.descriptors = set(root.descriptors)
    for child in root.childs:
        FinalizeCategory(child)
        root.descriptors.update(set(child.descriptors))

    root.descriptors = list(root.descriptors)
    root.descriptors.sort(key=functools.cmp_to_key(lambda a, b: basic_cmp(a.fileName, b.fileName)))


def AddDescRecurs(virtualDAT, catID, desc):
    if desc not in virtualDAT.categories[catID].descriptors:
        virtualDAT.categories[catID].descriptors.append(desc)
        if virtualDAT.categories[catID].parentID != 0:
            AddDescRecurs(virtualDAT, virtualDAT.categories[catID].parentID, desc)
