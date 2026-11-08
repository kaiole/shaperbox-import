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
        return [quoted or bare for quoted, bare in re.findall(r'"([^"]*)"|(\S+)', line)]
    try:
        return shlex.split(line)
    except ValueError:
        return [whole]


def ensure_closed(lib):
    apps = library.apps_using(lib)
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
                # History first, so --undo covers the preset even if adding it fails halfway.
                library.add_history({'hash': h, 'name': r['name'], 'source': r['source']})
                library.add_preset(db, lib, h, r['name'], tree)
            except Exception as e:
                print(f'  failed: {r["source"]}: {e}')
                continue
            done += 1
    print(f'\nDone! Imported {done} presets. Open ShaperBox and look under My Presets.')
    print(f'(Backup of your preset list: {backup})')


def run_undo(args, lib):
    ours = {r['hash'] for r in library.read_history()}
    with closing(library.connect(lib)) as db:
        hashes = [h for (h,) in db.execute('SELECT hash FROM presets') if h in ours]
    if not hashes:
        print('Nothing to undo: no presets imported by this tool are in your library.')
        return
    ensure_closed(lib)
    if not ask(f'Remove the {len(hashes)} presets this tool imported?', args.yes):
        print('Nothing changed.')
        return
    backup = library.backup(lib)
    with closing(library.connect(lib)) as db:
        library.remove_presets(db, lib, hashes)
    library.write_history([])
    print(f'Removed {len(hashes)} presets. (Backup of your preset list: {backup})')


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
    lib = os.path.expanduser(args.library) if args.library else library.find_library()
    if not os.path.exists(library.db_path(lib)):
        msg = (f"Couldn't find ShaperBox 3's preset library at {lib}\n"
               'Open ShaperBox 3 once in your DAW, then try again.')
        others = [folder for _, folder in library.preset_dbs()] if library.WINDOWS else []
        if others:
            msg += '\n\nOther Cableguys preset folders on this PC:\n' + '\n'.join(f'  {f}' for f in others)
        sys.exit(msg)
    with closing(library.connect(lib)) as db:
        problem = library.library_problem(db, lib)
    if problem:
        sys.exit(f"ShaperBox's library at {lib} doesn't look the way this tool expects ({problem}).\n"
                 'Nothing was changed.')
    if args.undo:
        run_undo(args, lib)
        return
    if not args.folders:
        args.folders = ask_for_folders(lib)
        if not args.folders:
            sys.exit('No folder given.')
    for f in args.folders:
        if not os.path.exists(os.path.expanduser(f)):
            sys.exit(f"Couldn't find {f}")
    run_import(args, lib)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit('\nStopped.')
