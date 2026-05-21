"""Small numeric and container helpers used across SC4PIM."""
from math import fmod


def basic_cmp(x, y) -> int:
    return (x > y) - (x < y)


def round_to_int(a):
    return int(round(a))


def clamp_to_tile(x):
    if fmod(x, 16) < 0.5 and x > 16:
        return int(x - 1) / 16 * 16 + 15.5
    return int(x) / 16 * 16 + min(fmod(x, 16), 15.5)


def test(condition, val_true, val_false):
    if condition:
        return val_true
    return val_false


def less_than(v1, v2):
    return v1 < v2


def greater_than(v1, v2):
    return v1 > v2


class DictWrapper(object):

    def __init__(self, mapping):
        object.__init__(self)
        object.__setattr__(self, 'mapping', mapping)

    def __getitem__(self, key):
        if isinstance(key, str):
            if key[:2].upper() == '0X':
                key = '0x' + key[2:10].upper() + key[10:]
        if key in self.mapping:
            return self.mapping[key]
        if isinstance(key, str):
            sub = key.find('.')
            if sub == -1:
                return ''
            k = key[0:sub]
            after = key[sub + 1:]
            return self.mapping[k][after]
        raise KeyError

    def __setitem__(self, key, value):
        self.mapping[key] = value

    def __getattr__(self, attr):
        if attr in self.mapping:
            return self.mapping[attr]
        raise AttributeError(attr)

    def __setattr__(self, attr, value):
        self.mapping[attr] = value

    def __str__(self):
        return str(self.mapping)

    def __repr__(self):
        return str(self.mapping)

    def update(self, other):
        self.mapping.update(other.mapping)

    def keys(self):
        return self.mapping.keys()

    def values(self):
        return self.mapping.values()

    def __len__(self):
        return len(self.mapping)
