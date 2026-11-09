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

WINDOWS = os.name == 'nt'
ZIP_MAGIC = b'#zip#\x00'
PRESET_EXTS = ('.fst', '.fxp', '.vstpreset')
# ShaperBox keeps its library in the user app-data folder: ~/Library on Mac, %APPDATA% on Windows.
# Our own files (import history + database backups) live outside ShaperBox's folder.
if WINDOWS:
    APPDATA = os.environ.get('APPDATA') or os.path.expanduser(r'~\AppData\Roaming')
    DEFAULT_LIBRARY = os.path.join(APPDATA, 'Cableguys', 'ShaperBox3')
    DATA_DIR = os.path.join(APPDATA, 'ShaperBox Import')
    # Searched when DEFAULT_LIBRARY isn't there, since that spot is unconfirmed on Windows.
    CABLEGUYS_DIRS = [os.path.join(d, 'Cableguys') for d in
                      dict.fromkeys((APPDATA, os.environ.get('LOCALAPPDATA'), os.environ.get('PROGRAMDATA'))) if d]
else:
    DEFAULT_LIBRARY = os.path.expanduser('~/Library/Cableguys/ShaperBox3')
    DATA_DIR = os.path.expanduser('~/Library/Application Support/ShaperBox Import')
HISTORY = os.path.join(DATA_DIR, 'history.csv')
HISTORY_FIELDS = ['hash', 'name', 'source']
# What add_preset() writes to; anything else means a ShaperBox version this tool doesn't know.
SCHEMA = {'presets': {'hash', 'name', 'author', 'liked', 'version', 'custom'},
          'queue': {'command', 'table_name', 'row_key', 'row_subkey', 'column', 'value', 'state'}}
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


def preset_folders():
    r"""Windows: the folders with a presets.db under CABLEGUYS_DIRS, as (ShaperBox 3's, the rest). Other Cableguys
    plugins keep theirs there too, nested deeper, e.g. Cableguys\VolumeShaper\3volumeshaper4\presets."""
    ours, others = [], []
    for root in CABLEGUYS_DIRS:
        for dp, _, files in os.walk(root):
            if any(f.lower() == 'presets.db' for f in files):
                shaperbox = 'shaperbox3' in os.path.relpath(dp, root).lower().replace(' ', '')
                (ours if shaperbox else others).append(dp)
    return ours, others


def connect(lib):
    return sqlite3.connect(db_path(lib), timeout=5)


def library_problem(db, lib):
    """Why this doesn't look like a library add_preset() can write to, or None if it does."""
    for table, columns in SCHEMA.items():
        if not columns <= {r[1] for r in db.execute(f'PRAGMA table_info({table})')}:
            return f'the {table} table is different'
    sample = [dat_path(lib, h) for (h,) in db.execute('SELECT hash FROM presets LIMIT 20')]
    if sample and not any(is_preset_file(p) for p in sample):
        return "preset files aren't where they should be"
    return None


def is_preset_file(path):
    try:
        with open(path, 'rb') as f:
            return f.read(len(ZIP_MAGIC)) == ZIP_MAGIC
    except OSError:
        return False


def apps_using(lib):
    """Names of other programs that have the preset database open (e.g. a DAW running ShaperBox)."""
    if WINDOWS:
        return ['another program (most likely your DAW)'] if open_elsewhere(db_path(lib)) else []
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


def open_elsewhere(path, wait=2):
    """Windows: True if any program (ours included) keeps path open. Windows can't cheaply say which
    program, but opening a file with no sharing allowed fails while anything else holds it. A virus
    scanner or the search indexer holds it only briefly, so that has to last `wait` seconds to count.
    Raises OSError when the open fails for any other reason, since then there's no telling."""
    # Not _winapi.CreateFile: on older Pythons (3.9, 3.10) it calls the ANSI API, which garbles non-ASCII paths
    # (a username like Zoë) so the open fails for the wrong reason and the check passes.
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    deadline = time.monotonic() + wait
    while True:
        h = k32.CreateFileW(path, 0x80000000, 0, None, 3, 0, None)  # GENERIC_READ, no sharing, OPEN_EXISTING
        if h != wintypes.HANDLE(-1).value:  # INVALID_HANDLE_VALUE
            k32.CloseHandle(h)
            return False
        err = ctypes.get_last_error()
        if err != 32:  # ERROR_SHARING_VIOLATION
            raise ctypes.WinError(err)
        if time.monotonic() >= deadline:
            return True
        time.sleep(0.25)


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


def add_preset(db, lib, h, name, tree):
    # h comes from new_hash(). Author stays empty: ShaperBox only shows author-less presets under My Presets.
    tags = module_tags(tree)
    version, blob = prepare(tree, name)
    path = dat_path(lib, h)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'wb') as f:
            f.write(blob)
        with db:
            db.execute("INSERT INTO presets(hash,name,author,liked,version,custom) VALUES(?,?,'','0',?,?)",
                       (h, name, version, tags))
            q = ("INSERT INTO queue(command,table_name,row_key,row_subkey,column,value,state)"
                 " VALUES(?,'presets',?,'',?,?,0)")
            db.execute(q, ('new__begin', h, '', ''))
            for col, val in (('author', ''), ('custom', tags), ('liked', '0'), ('name', name),
                             ('version', str(version))):
                db.execute(q, ('new__part', h, col, val))
            db.execute(q, ('new__end', h, '', ''))
    except BaseException:  # Ctrl+C too
        # Don't leave a file behind that ShaperBox's list doesn't know about. If that fails as well, --undo gets it.
        try:
            if not db.execute('SELECT 1 FROM presets WHERE hash=?', (h,)).fetchone():
                os.remove(path)
        except (OSError, sqlite3.Error):
            pass
        raise


def remove_presets(db, lib, hashes):
    """Returns the hashes whose .dat file couldn't be deleted; those are out of ShaperBox's list all the same."""
    with db:
        for h in hashes:
            db.execute('DELETE FROM presets WHERE hash=?', (h,))
            db.execute('DELETE FROM queue WHERE row_key=?', (h,))
    stuck = []
    for h in hashes:
        try:
            os.remove(dat_path(lib, h))
        except FileNotFoundError:
            pass
        except OSError:  # held open by another program, or read-only
            stuck.append(h)
    return stuck


def read_history():
    if not os.path.exists(HISTORY):
        return []
    with open(HISTORY, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_history(rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def add_history(row):
    if not os.path.exists(HISTORY):
        write_history([])
    with open(HISTORY, 'a', newline='', encoding='utf-8') as f:
        csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction='ignore').writerow(row)
