"""Turn folders of preset files into ShaperBox preset names: "PACK - name".

PACK is the folder a preset sits in, upper-cased. Folders that only describe the file format
(e.g. "FXP FILES", "presets") are skipped in favour of the folder above them. A preset that
appears more than once (say as both .fst and .fxp) is imported once.
"""
import os
import re

from . import library
from .fingerprint import fingerprint, sound_fingerprint

FORMAT_WORDS = {'fxp', 'fst', 'vst', 'vst2', 'vst3', 'vstpreset', 'vstpresets', 'files',
                'preset', 'presets', 'shaperbox', 'shaperbox3', 'sb', 'sb3', '3'}
PREFERRED_EXTS = ('.fst', '.vstpreset', '.fxp')
TAG_RE = re.compile(r'\s*(?:\[([^\]]+)\]|@(\w+))\s*')  # creator tags: "[name]" or "@name"
SUFFIX_RE = re.compile(r'\s+-\s*([^-]+?)\s*$')  # "WIPE - J3ST4RRR", "DATAMIST -HITGIRL"; not "LO-FI"


def is_format_folder(name):
    return all(w in FORMAT_WORDS for w in re.findall(r'[a-z0-9]+', name.lower()))


def pack_name(path, root):
    parts = [p for p in os.path.relpath(os.path.dirname(path), root).split(os.sep)
             if p != '.' and not is_format_folder(p)]
    if not parts:  # preset sits directly in the chosen folder (or in format folders below it)
        d = root
        while is_format_folder(os.path.basename(d)) and os.path.dirname(d) != d:
            d = os.path.dirname(d)
        parts = [os.path.basename(d)]
    label = ' '.join(p.lstrip('!') for p in parts).upper()
    return label.replace(' PRESETS', '').strip() or 'PRESETS'  # "HXH PRESETS" -> HXH


def clean_name(stem):
    name = TAG_RE.sub(' ', stem)
    return ' '.join(name.split()).strip(' -')


def strip_creator_suffix(names):
    """Drop a trailing " - CREATOR" in packs where most presets end in one: an ending that appears
    on 2+ presets is a creator tag, as long as such endings cover at least half the pack."""
    ends = [SUFFIX_RE.search(n) for n in names]
    key = lambda m: re.sub(r'\s*\(\d+\)$', '', m.group(1)).casefold()
    counts = {}
    for m in filter(None, ends):
        counts[key(m)] = counts.get(key(m), 0) + 1
    tagged = [bool(m and counts[key(m)] > 1 and not m.group(1).isdigit()) for m in ends]
    if sum(tagged) * 2 < len(names):
        return names
    return [n[:m.start()] if t else n for n, m, t in zip(names, ends, tagged)]


def strip_shared_prefix(names):
    """Drop a leading "XYZ - " that every preset in the pack shares (it repeats the pack name)."""
    prefixes = {m.group(1) if m else None for m in (re.match(r'^(.*? - )', n) for n in names)}
    if len(prefixes) == 1 and None not in prefixes and len(names) > 1:
        p = prefixes.pop()
        return strip_shared_prefix([n[len(p):] for n in names])
    return names


def pad_numbers(names):
    """"1", "2" ... "10" -> "01", "02" ... "10" so they sort in order."""
    nums = [n for n in names if n.isdigit()]
    if not nums:
        return names
    width = max(2, len(max(nums, key=len)))
    return [n.zfill(width) if n.isdigit() else n for n in names]


def plan(folders):
    """Returns ([{pack, name, source, duplicates}], [(path, error)]) for everything under folders."""
    files = {}
    for folder in folders:
        folder = os.path.abspath(os.path.expanduser(folder))
        root = folder if os.path.isdir(folder) else os.path.dirname(folder)
        for p in library.find_presets(folder):
            files.setdefault(p, root)

    groups, sounds, failed = {}, {}, []
    for p in sorted(files):
        try:
            tree = library.read_state(p)
        except Exception as e:
            failed.append((p, str(e)))
            continue
        fp = fingerprint(tree)
        groups.setdefault(fp, []).append(p)
        try:
            sounds[fp] = sound_fingerprint(tree)
        except Exception:
            sounds[fp] = fp

    # Same pack + same file name + same sound -> one preset (e.g. a .fst and .fxp exported by
    # different ShaperBox versions that only differ in switched-off modules).
    merged = {}
    for fp, paths in groups.items():
        p = paths[0]
        key = (pack_name(p, files[p]), clean_name(os.path.splitext(os.path.basename(p))[0]).casefold(), sounds[fp])
        merged.setdefault(key, []).extend(paths)

    packs = {}
    for (pack, _, _), paths in merged.items():
        paths.sort(key=lambda p: (PREFERRED_EXTS.index(os.path.splitext(p)[1].lower()), len(p), p))
        packs.setdefault(pack, []).append(paths)

    rows = []
    for pack in sorted(packs):
        entries = sorted(packs[pack], key=lambda ps: os.path.basename(ps[0]).casefold())
        names = [clean_name(os.path.splitext(os.path.basename(ps[0]))[0]) for ps in entries]
        names = pad_numbers(strip_shared_prefix(strip_creator_suffix(names)))
        for ps, name in zip(entries, names):
            rows.append({'pack': pack, 'name': f'{pack} - {name or "untitled"}',
                         'source': ps[0], 'duplicates': ps[1:]})

    seen = {}
    for r in rows:
        key = r['name'].casefold()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            r['name'] += f' ({seen[key]})'
    return rows, failed
