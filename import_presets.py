#!/usr/bin/env python3
"""Import ShaperBox 3 preset files (.fst, .fxp, .vstpreset) into ShaperBox's My Presets.

  python3 import_presets.py FOLDER            import every preset in FOLDER (and its subfolders)
  python3 import_presets.py --preview FOLDER  only show the names they would get
  python3 import_presets.py --undo            remove everything this tool has imported
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sbimport import library, naming  # noqa: E402


def ask(question, assume_yes):
    if assume_yes:
        return True
    try:
        return input(f'{question} (y/n) ').strip().lower() in ('y', 'yes')
    except EOFError:
        return False


def ensure_closed(lib):
    apps = library.apps_using(lib)
    if apps:
        sys.exit(f'\nShaperBox is open in: {", ".join(apps)}\nQuit it first, then run this again.')


def run_import(args, lib):
    rows, failed = naming.plan(args.folders)
    if not rows:
        sys.exit('No ShaperBox 3 presets (.fst, .fxp, .vstpreset) found there.')

    db = sqlite3.connect(library.db_path(lib), timeout=5)
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
    for r in new:
        try:
            tree = library.read_state(r['source'])
            h = library.add_preset(db, lib, r['name'], tree)
        except Exception as e:
            print(f'  failed: {r["source"]}: {e}')
            continue
        library.add_history({'hash': h, 'name': r['name'], 'source': r['source']})
        done += 1
    db.close()
    print(f'\nDone! Imported {done} presets. Open ShaperBox and look under My Presets.')
    print(f'(Backup of your preset list: {backup})')


def run_undo(args, lib):
    db = sqlite3.connect(library.db_path(lib), timeout=5)
    ours = {r['hash'] for r in library.read_history()}
    hashes = [h for (h,) in db.execute('SELECT hash FROM presets') if h in ours]
    if not hashes:
        print('Nothing to undo: no presets imported by this tool are in your library.')
        return
    ensure_closed(lib)
    if not ask(f'Remove the {len(hashes)} presets this tool imported?', args.yes):
        print('Nothing changed.')
        return
    backup = library.backup(lib)
    library.remove_presets(db, lib, hashes)
    library.write_history([])
    db.close()
    print(f'Removed {len(hashes)} presets. (Backup of your preset list: {backup})')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folders', nargs='*', help='folders (or files) with presets')
    ap.add_argument('--preview', action='store_true', help='show what would be imported, change nothing')
    ap.add_argument('--undo', action='store_true', help='remove every preset this tool imported')
    ap.add_argument('--yes', action='store_true', help="don't ask before changing anything")
    ap.add_argument('--library', default=library.DEFAULT_LIBRARY, help='ShaperBox 3 library folder')
    args = ap.parse_args()

    lib = os.path.expanduser(args.library)
    if not os.path.exists(library.db_path(lib)):
        sys.exit(f"Couldn't find ShaperBox 3's preset library at {lib}\n"
                 'Open ShaperBox 3 once in your DAW, then try again.')
    if args.undo:
        run_undo(args, lib)
    elif args.folders:
        for f in args.folders:
            if not os.path.exists(os.path.expanduser(f)):
                sys.exit(f"Couldn't find {f}")
        run_import(args, lib)
    else:
        ap.print_help()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit('\nStopped.')
