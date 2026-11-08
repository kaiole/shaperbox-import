"""Content fingerprint of a ShaperBox state: ignores name/timestamp/version metadata and UI selection."""
import hashlib
from . import vtree

UI_ONLY = {'SelectedWaveId', 'PluginStateMetaData'}


def strip(t):
    return vtree.Tree(t.type, list(t.props), [strip(c) for c in t.children if c.type not in UI_ONLY])


def fingerprint(tree):
    t = strip(tree)
    t.props = []
    return hashlib.sha1(vtree.write_tree(t)).hexdigest()


def sound_fingerprint(tree):
    """Looser: only switched-on modules (in chain order) and global settings. Ignores the state of
    switched-off modules, which differs between ShaperBox versions without changing the sound."""
    t = strip(tree)
    flags = lambda c: {g.get('id'): g.get('value') for g in c.children if g.type == 'bool'}
    modules = [c for c in t.children if c.type.endswith('State') and 'on' in flags(c)]
    slots = [g.get('value') for g in next(c for c in t.children if c.get('id') == 'moduleSlots').children]
    active = [modules[i] for i in slots if i < len(modules) and flags(modules[i])['on']]
    rest = [c for c in t.children if c not in modules and c.get('id') != 'moduleSlots']
    return hashlib.sha1(b''.join(vtree.write_tree(c) for c in active + rest)).hexdigest()
