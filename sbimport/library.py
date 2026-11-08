"""Read preset files and write them into ShaperBox 3's preset library.

The library is a folder holding a SQLite database (presets.db) and one compressed state file per
preset at <h0>/<h1>/<hash>.dat. Saving a preset in ShaperBox writes the .dat file, a row in
`presets`, and new__begin/new__part/new__end rows in `queue`; add_preset() does the same.
"""
import csv
import os
import secrets
import sqlite3
import subprocess
import time
import zlib

from . import vtree

ZIP_MAGIC = b'#zip#\x00'
PRESET_EXTS = ('.fst', '.fxp', '.vstpreset')
DEFAULT_LIBRARY = os.path.expanduser('~/Library/Cableguys/ShaperBox3')
# Our own files (import history + database backups) live outside ShaperBox's folder.
DATA_DIR = os.path.expanduser('~/Library/Application Support/ShaperBox Import')
HISTORY = os.path.join(DATA_DIR, 'history.csv')
HISTORY_FIELDS = ['hash', 'name', 'source']
# Order ShaperBox uses for the `custom` (module tag) column; module ids renamed in tags.
TAG_ORDER = ['time', 'pitch', 'drive', 'noise', 'filter', 'liquid', 'crush', 'volume',
             'pan', 'reverb', 'width', 'compressor', 'oscilloscope']
TAG_RENAME = {'dynamics': 'compressor'}


def read_state(path):
    """The ShaperBox state embedded in a .fst / .fxp / .vstpreset file."""
    with open(path, 'rb') as f:
        raw = f.read()
    if raw.count(ZIP_MAGIC) != 1:
        raise ValueError('not a ShaperBox 3 preset')
    d = zlib.decompressobj()
    body = d.decompress(raw[raw.index(ZIP_MAGIC) + len(ZIP_MAGIC):])
    if not d.eof:
        raise ValueError('file is cut off or damaged')
    tree, rest = vtree.parse(body)
    if tree.type != 'PluginState' or rest:
        raise ValueError('not a ShaperBox 3 preset')
    return tree


def module_tags(tree):
    """Modules ShaperBox lists for the preset: switched on and shown in the module bar."""
    tags = []
    for c in tree.children:
        if not c.type.endswith('State') or not c.get('id'):
            continue
        flags = {g.get('id'): g.get('value') for g in c.children if g.type == 'bool'}
        if flags.get('on') and flags.get('VISIBLE'):
            tags.append(TAG_RENAME.get(c.get('id'), c.get('id')))
    known = [t for t in TAG_ORDER if t in tags]
    return ','.join(known + [t for t in tags if t not in TAG_ORDER])


def prepare(tree, name):
    """Mirror what ShaperBox does on save: set name, drop ProgramTag, refresh timestamp."""
    version = tree.get('version')
    others = [(k, v) for k, v in tree.props if k not in ('version', 'ProgramName', 'ProgramTag', 'timestamp')]
    tree.props = []
    tree.set_string('version', str(version))
    tree.set_string('ProgramName', name)
    tree.set_int64('timestamp', int(time.time() * 1000))
    tree.props += others
    return int(version), ZIP_MAGIC + zlib.compress(vtree.write_tree(tree))


def find_presets(path):
    if os.path.isfile(path):
        return [path] if path.lower().endswith(PRESET_EXTS) else []
    files = []
    for dp, _, fs in os.walk(path):
        files += [os.path.join(dp, f) for f in fs if f.lower().endswith(PRESET_EXTS)]
    return sorted(files)


def db_path(lib):
    return os.path.join(lib, 'presets.db')


def dat_path(lib, h):
    return os.path.join(lib, h[0], h[1], h + '.dat')


def apps_using(lib):
    """Names of other programs that have the preset database open (e.g. a DAW running ShaperBox)."""
    try:
        out = subprocess.run(['lsof', '-Fpc', db_path(lib)], capture_output=True, text=True).stdout
    except OSError:
        return []
    apps, pid = set(), None
    for line in out.splitlines():
        if line.startswith('p'):
            pid = int(line[1:])
        elif line.startswith('c') and pid != os.getpid():
            apps.add(line[1:])
    return sorted(apps)


def backup(lib):
    """Snapshot presets.db; the .dat files are never modified, only added (import) or removed (undo)."""
    folder = os.path.join(DATA_DIR, 'backups')
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, time.strftime('presets-%Y-%m-%d-%H%M%S.db'))
    src, dst = sqlite3.connect(db_path(lib)), sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return dest


def preset_names(db):
    return {n.casefold() for (n,) in db.execute('SELECT name FROM presets')}


def new_hash(db, lib):
    while True:
        h = secrets.token_hex(16)
        if not db.execute('SELECT 1 FROM presets WHERE hash=?', (h,)).fetchone() \
                and not os.path.exists(dat_path(lib, h)):
            return h


def add_preset(db, lib, name, tree):
    # Author stays empty: ShaperBox only shows author-less presets under My Presets.
    tags = module_tags(tree)
    version, blob = prepare(tree, name)
    h = new_hash(db, lib)
    path = dat_path(lib, h)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(blob)
    with db:
        db.execute("INSERT INTO presets(hash,name,author,liked,version,custom) VALUES(?,?,'','0',?,?)",
                   (h, name, version, tags))
        q = "INSERT INTO queue(command,table_name,row_key,row_subkey,column,value,state) VALUES(?,'presets',?,'',?,?,0)"
        db.execute(q, ('new__begin', h, '', ''))
        for col, val in (('author', ''), ('custom', tags), ('liked', '0'), ('name', name), ('version', str(version))):
            db.execute(q, ('new__part', h, col, val))
        db.execute(q, ('new__end', h, '', ''))
    return h


def remove_presets(db, lib, hashes):
    with db:
        for h in hashes:
            db.execute('DELETE FROM presets WHERE hash=?', (h,))
            db.execute('DELETE FROM queue WHERE row_key=?', (h,))
    for h in hashes:
        if os.path.exists(dat_path(lib, h)):
            os.remove(dat_path(lib, h))


def read_history():
    if not os.path.exists(HISTORY):
        return []
    with open(HISTORY, newline='') as f:
        return list(csv.DictReader(f))


def write_history(rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def add_history(row):
    if not os.path.exists(HISTORY):
        write_history([])
    with open(HISTORY, 'a', newline='') as f:
        csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction='ignore').writerow(row)
