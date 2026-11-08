# ShaperBox Preset Importer

Imports ShaperBox 3 presets (`.fst`, `.fxp`, `.vstpreset`) into My Presets in bulk. Mac only.

## Usage

1. Click the green **Code** button above, then **Download ZIP**. Unzip it.
2. Quit your DAW.
3. Double-click **Import Presets.command**.
4. Drag your preset folder into the window, press Enter, then type `y`.

Presets are named `FOLDER - preset name`. Subfolders are included. Presets already in your library are skipped.

## If macOS blocks it

The first time, macOS says it can't verify the file. Click **Done**, then go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to "Import Presets.command". You only need to do this once.

If macOS asks to install command line developer tools, install them and run it again.

## Other commands

From Terminal:

```
python3 import_presets.py --preview path/to/presets   # show names, import nothing
python3 import_presets.py --undo                      # remove everything this tool imported
```

## Notes

- Your preset list is backed up before every change to `~/Library/Application Support/ShaperBox Import/backups`.
- Not affiliated with Cableguys.
