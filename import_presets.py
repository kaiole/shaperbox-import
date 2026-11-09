#!/usr/bin/env python3
"""Import ShaperBox 3 preset files (.fst, .fxp, .vstpreset) into ShaperBox's My Presets.

  python3 import_presets.py FOLDER            import every preset in FOLDER (and its subfolders)
  python3 import_presets.py                   same, but asks for the folder (drag it into the window)
  python3 import_presets.py --preview FOLDER  only show the names they would get
  python3 import_presets.py --undo            remove everything this tool has imported

On Windows, type py -3 instead of python3.
"""
import argparse
import os
import re
import shlex
import sqlite3
import sys
from contextlib import closing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sbimport import library, naming  # noqa: E402


def ask(question, assume_yes):
    if assume_yes:
        return True
    try:
        return input(f'{question} (y/n) ').strip().lower() in ('y', 'yes')
    except EOFError:
        return False


def ask_for_folders(lib):
    print(f'ShaperBox Preset Importer\nLibrary: {lib}\n\nQuit your DAW first.\n\n'
          'Drag your preset folder into this window, then press Enter:')
    try:
        line = input()
    except EOFError:
        return []
    print()
    return split_paths(line)


def split_paths(line):
    r"""Paths the way a terminal pastes dragged items: My\ Presets on Mac, "C:\My Presets" on Windows."""
    whole = line.strip().strip('"\'')
    if not whole or os.path.exists(os.path.expanduser(whole)):
        return [whole] if whole else []
    if library.WINDOWS:
        # PowerShell pastes 'C:\My Presets' instead, with any ' doubled. A quoted path can follow a bare one
        # with no space between, so a bare one stops at a ".
        found = re.findall(r'''"([^"]*)"|'((?:[^']|'')*)'|([^\s"]+)''', line)
        return [p for p in (dq or sq.replace("''", "'") or bare for dq, sq, bare in found) if p]
    try:
        return shlex.split(line)
    except ValueError:
        return [whole]


def ensure_closed(lib):
    try:
        apps = library.apps_using(lib)
    except OSError as e:
        sys.exit(f"\nCouldn't check whether ShaperBox is open ({e}).\nNothing was changed.")
    if apps:
        sys.exit(f'\nShaperBox is open in: {", ".join(apps)}\nQuit it first, then run this again.')


def run_import(args, lib):
    rows, failed = naming.plan(args.folders)
    if not rows:
        sys.exit('No ShaperBox 3 presets (.fst, .fxp, .vstpreset) found there.')

    with closing(library.connect(lib)) as db:
        existing = library.preset_names(db)
    new = [r for r in rows if r['name'].casefold() not in existing]
    skipped = len(rows) - len(new)

    packs = {}
    for r in new:
        packs[r['pack']] = packs.get(r['pack'], 0) + 1
    if args.preview:
        for r in new:
            print(f'  {r["name"]}')
        print()
    for pack, n in packs.items():
        print(f'  {pack:<30} {n} presets')
    print(f'\n{len(new)} new presets.', end='')
    if skipped:
        print(f' {skipped} skipped (already in your library).', end='')
    print()
    for path, err in failed:
        print(f'  could not read {path}: {err}')

    if args.preview or not new:
        return
    ensure_closed(lib)
    if not ask(f'\nImport {len(new)} presets into ShaperBox?', args.yes):
        print('Nothing changed.')
        return

    backup = library.backup(lib)
    done = 0
    with closing(library.connect(lib)) as db:
        for r in new:
            try:
                tree = library.read_state(r['source'])
                h = library.new_hash(db, lib)
                # History first, so --undo covers the preset's file even if adding it is cut short.
                library.add_history({'hash': h, 'name': r['name'], 'source': r['source']})
                library.add_preset(db, lib, h, r['name'], tree)
            except Exception as e:
                print(f'  failed: {r["source"]}: {e}')
                continue
            done += 1
    print(f'\nDone! Imported {done} presets. Open ShaperBox and look under My Presets.')
    print(f'(Backup of your preset list: {backup})')


def run_undo(args, lib):
    # history.csv can be edited or damaged; only real hashes get turned into file paths.
    ours = {r['hash'] for r in library.read_history() if re.fullmatch('[0-9a-f]{32}', r['hash'] or '')}
    with closing(library.connect(lib)) as db:
        listed = {h for (h,) in db.execute('SELECT hash FROM presets')}
    # Not only the listed ones: an import that was cut short, or an earlier undo, can leave just the file.
    hashes = sorted(h for h in ours if h in listed or os.path.exists(library.dat_path(lib, h)))
    if not hashes:
        print('Nothing to undo: no presets imported by this tool are in your library.')
        return
    ensure_closed(lib)
    if not ask(f'Remove the {len(hashes)} presets this tool imported?', args.yes):
        print('Nothing changed.')
        return
    backup = library.backup(lib)
    with closing(library.connect(lib)) as db:
        stuck = set(library.remove_presets(db, lib, hashes))
    library.write_history([r for r in library.read_history() if r['hash'] in stuck])
    print(f'Removed {len(hashes) - len(stuck)} presets. (Backup of your preset list: {backup})')
    if stuck:
        print(f"{len(stuck)} more are gone from ShaperBox's list, but their files couldn't be deleted\n"
              '(in use by another program, or read-only). Run --undo again later to delete them.')


def pick_library(args):
    """The library folder to use. Exits with what was found if it's missing or there's more than one."""
    lib = os.path.expanduser(args.library) if args.library else library.DEFAULT_LIBRARY
    if os.path.exists(library.db_path(lib)):
        return lib
    ours, others = library.preset_folders() if library.WINDOWS else ([], [])
    if not args.library and len(ours) == 1:
        return ours[0]

    def listing(title, folders):
        return f'\n\n{title}\n' + '\n'.join(f'  {f}' for f in folders) if folders else ''

    if not args.library and ours:
        sys.exit('Found more than one ShaperBox 3 preset library on this PC.'
                 + listing('The libraries:', ours)
                 + '\n\nTo use one of them, open Command Prompt in this folder and run this with its path:\n'
                 f'  py -3 import_presets.py --library "{ours[0]}"')
    sys.exit(f"Couldn't find ShaperBox 3's preset library at {lib}\n"
             'Open ShaperBox 3 once in your DAW, then try again.'
             + listing('ShaperBox 3 preset folders on this PC:', ours)
             + listing('Other Cableguys preset folders on this PC:', others))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='replace')  # a name the window can't show shouldn't stop an import
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folders', nargs='*', help='folders (or files) with presets')
    ap.add_argument('--preview', action='store_true', help='show what would be imported, change nothing')
    ap.add_argument('--undo', action='store_true', help='remove every preset this tool imported')
    ap.add_argument('--yes', action='store_true', help="don't ask before changing anything")
    ap.add_argument('--library', help='ShaperBox 3 library folder (the one with presets.db)')
    args = ap.parse_args()

    if library.WINDOWS and '\\windowsapps\\' in sys.base_prefix.lower():
        # Store Python is sandboxed: new files it makes under AppData go to a private copy ShaperBox never sees.
        sys.exit("This Python is the Microsoft Store version, which can't save into ShaperBox's folder.\n"
                 'Install Python from python.org/downloads and uninstall the Store one\n'
                 '(Settings > Apps > Installed apps), then run this again.')
    lib = pick_library(args)
    try:
        if args.undo:
            run_undo(args, lib)
            return
        if not args.preview:
            # Only importing writes everything this checks; --undo and --preview have to work without it.
            with closing(library.connect(lib)) as db:
                problem = library.library_problem(db, lib)
            if problem:
                sys.exit(f"ShaperBox's library at {lib} doesn't look the way this tool expects ({problem}).\n"
                         'Nothing was changed.')
        if not args.folders:
            args.folders = ask_for_folders(lib)
            if not args.folders:
                sys.exit('No folder given.')
        for f in args.folders:
            if not os.path.exists(os.path.expanduser(f)):
                sys.exit(f"Couldn't find {f}")
        run_import(args, lib)
    except sqlite3.Error as e:
        if 'locked' in str(e):
            sys.exit("\nShaperBox's preset list is in use by another program, most likely your DAW.\n"
                     'Quit it first, then run this again.')
        sys.exit(f"\nCouldn't read ShaperBox's preset list at {library.db_path(lib)} ({e}).\nNothing was changed.")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit('\nStopped.')
