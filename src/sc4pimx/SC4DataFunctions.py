import functools
import struct

from util import DictWrapper, basic_cmp
from translation import categoryLocalized


def ReadStageVsDensity(node):
    purpose = str(node.getAttribute('purpose'))
    wealth = int(node.getAttribute('wealth'))
    ratio = [float(x) for x in str(node.getAttribute('ratio')).split(',')]
    baseTex = int(node.getAttribute('baseTex'), 16)
    return (
        ratio, purpose, wealth, baseTex)


def ReadZoning(node):
    purpose = str(node.getAttribute('purpose'))
    value = int(node.getAttribute('value'))
    stages = [int(x) for x in str(node.getAttribute('stages')).split(',')]
    height = int(node.getAttribute('height'))
    return (
        purpose, value, stages, height)


def readPropertyDef(node):
    prop = DictWrapper({})
    prop.Name = str(node.getAttribute('Name'))
    id = node.getAttribute('ID').upper()
    if id[:2] == '0X':
        prop.ID = int(node.getAttribute('ID'), 16)
    else:
        prop.ID = node.getAttribute('ID').upper()
    prop.Type = str(node.getAttribute('Type'))
    count = node.getAttribute('Count').upper()
    if count == '':
        count = '1'
    prop.Count = int(count)
    if node.getAttribute('ShowAsHex').upper() == 'Y':
        prop.ShowAsHex = True
    else:
        prop.ShowAsHex = False
    options = {}
    prop.ShowAsMap = False
    minVal = node.getAttribute('MinValue')
    maxVal = node.getAttribute('MaxValue')
    if minVal is None or minVal == '':
        if prop.Type == 'Uint32' or prop.Type == 'Uint8':
            minVal = 0
        if prop.Type == 'Sint32' or prop.Type == 'Sint64':
            minVal = -100000000
        if prop.Type == 'Float32':
            minVal = -100000000.0
    else:
        if len(minVal) > 1 and minVal[1] == 'x':
            minVal = int(minVal, 16)
        else:
            minVal = int(minVal)
        if maxVal is None or maxVal == '':
            if prop.Type == 'Uint32':
                maxVal = 4294967295
            if prop.Type == 'Uint8':
                maxVal = 255
            if prop.Type == 'Sint32':
                maxVal = 2147483647
            if prop.Type == 'Sint64':
                maxVal = 9223372036854775807
            if prop.Type == 'Float32':
                maxVal = 100000000.0
        elif len(maxVal) > 1 and maxVal[1] == 'x':
            maxVal = int(maxVal, 16)
        else:
            maxVal = int(maxVal)
        prop.maxVal = maxVal
        prop.minVal = minVal
        for subNode in node.childNodes:
            if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == 'FORMAT':
                prop.ShowAsMap = True
            if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == 'OPTION':
                value = subNode.getAttribute('Value').upper()
                if value[:3] == 'COL':
                    pass
                elif len(value) > 2 and value[1] == 'X':
                    value = int('0x' + value[2:], 16)
                else:
                    value = int(value)
                meaning = subNode.getAttribute('Name')
                options[value] = meaning

    prop.Options = options
    return prop


def ToUnsigned(val):
    try:
        return struct.unpack('L', struct.pack('l', val))[0]
    except:
        print(type(val), val)
        raise


def ToTile(val):
    try:
        return float(struct.unpack('l', struct.pack('L', int(val)))[0]) / float(1048576)
    except:
        print(type(val), val)
        raise


def ToCoord(val):
    return ToTile(val) * 16.0


def getText(nodelist):
    rc = ''
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data

    return rc


def readCategoryDef(node):
    cat = DictWrapper({})
    cat.descriptors = []
    cat.parent = None
    cat.imgName = None
    cat.imgIdx = None
    cat.imgName = node.getAttribute('img')
    cat.Name = node.getAttribute('Name')
    id = node.getAttribute('ID').upper()
    if id[:2] == '0X':
        cat.ID = int(node.getAttribute('ID'), 16)
    else:
        cat.ID = node.getAttribute('ID').upper()
    parentID = node.getAttribute('ParentID').upper()
    if parentID[:2] == '0X':
        cat.parentID = int(node.getAttribute('ParentID'), 16)
    else:
        cat.parentID = node.getAttribute('ParentID').upper()
    if cat.ID in categoryLocalized:
        cat.Name = categoryLocalized[cat.ID]
    cat.code = []
    cat.childs = []
    cat.filters = DictWrapper({})
    cat.filters.needed = []
    cat.filters.notallowed = []
    cat.setProperties = DictWrapper({})
    cat.factorProperties = DictWrapper({})
    cat.pairedFactorProperties = DictWrapper({})
    cat.programProperties = DictWrapper({})
    cat.evalProperties = DictWrapper({})
    cat.removeProperties = DictWrapper({})
    for subNode in node.childNodes:
        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == 'PROPERTIES':
            for subsubNode in subNode.childNodes:
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == 'eval':
                    name = subsubNode.getAttribute('name')
                    expr = subsubNode.getAttribute('value')
                    cat.code.append((name, expr))
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == 'PROPERTY':
                    id = subsubNode.getAttribute('ID').upper()
                    if id[:2] == '0X':
                        id = int(id.lower(), 16)
                    else:
                        id = int(id)
                    removep = subsubNode.getAttribute('Remove')
                    if removep == '':
                        removep = None
                    else:
                        cat.removeProperties[id] = removep
                    value = subsubNode.getAttribute('Value')
                    if value == '':
                        value = None
                    if value:
                        cat.setProperties[id] = value
                    factor = subsubNode.getAttribute('Factor')
                    if factor == '':
                        factor = None
                    if factor:
                        cat.factorProperties[id] = [float(f) for f in factor.split(',')]
                    pairedFactor = subsubNode.getAttribute('PairedFactor')
                    if pairedFactor == '':
                        pairedFactor = None
                    if pairedFactor:
                        paired = pairedFactor.split(',')
                        cat.pairedFactorProperties[id] = []
                        for i in range(len(paired) / 2):
                            cat.pairedFactorProperties[id].append((paired[i * 2], float(paired[i * 2 + 1])))

                    setVal = subsubNode.getAttribute('Set')
                    if setVal == '':
                        setVal = None
                    if setVal:
                        cat.programProperties[id] = setVal
                    evalVal = subsubNode.getAttribute('Eval')
                    if evalVal == '':
                        evalVal = None
                    if evalVal:
                        cat.evalProperties[id] = evalVal

        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == 'FILTERS':
            for subsubNode in subNode.childNodes:
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == 'NEEDED':
                    id = subsubNode.getAttribute('ID').upper()
                    if id[:2] == '0X':
                        id = int(id.lower(), 16)
                    else:
                        id = int(id)
                    value = subsubNode.getAttribute('Value')
                    if value == '':
                        value = None
                    if value:
                        value = value.upper()
                        if value[:2] == '0X':
                            value = int(value.lower(), 16)
                        else:
                            value = int(value)
                    cat.filters.needed.append((id, value))
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == 'NOT':
                    id = subsubNode.getAttribute('ID').upper()
                    if id[:2] == '0X':
                        id = int(id.lower(), 16)
                    else:
                        id = int(id)
                    value = subsubNode.getAttribute('Value')
                    if value == '':
                        value = None
                    if value:
                        value = value.upper()
                        if value[:2] == '0X':
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
    prop.maxVal = dup.maxVal if hasattr(dup, 'maxVal') else None
    prop.minVal = dup.minVal if hasattr(dup, 'minVal') else None
    prop.Options = dup.Options
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
