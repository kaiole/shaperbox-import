# ShaperBox Preset Importer

Imports ShaperBox 3 presets (`.fst`, `.fxp`, `.vstpreset`) into My Presets in bulk. Mac only.

## Usage

1. Quit your DAW.
2. Open Terminal and run:

   ```
   python3 path/to/import_presets.py path/to/presets
   ```

   You can drag the file and the folder into Terminal instead of typing the paths.

3. Type `y` to confirm.

Presets are named `FOLDER - preset name`. Subfolders are included. Presets already in your library are skipped.

## Other commands

```
python3 import_presets.py --preview path/to/presets   # show names, import nothing
python3 import_presets.py --undo                      # remove everything this tool imported
```

## Notes

- If macOS asks to install command line developer tools, install them and run the command again.
- Your preset list is backed up before every change to `~/Library/Application Support/ShaperBox Import/backups`.
- Not affiliated with Cableguys.
