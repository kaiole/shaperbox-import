# ShaperBox Preset Importer

Imports ShaperBox 3 presets (`.fst`, `.fxp`, `.vstpreset`) into My Presets in bulk. Mac and Windows.

## Mac

1. Click the green **Code** button above, then **Download ZIP**. Unzip it.
2. Quit your DAW.
3. Double-click **Import Presets.command**.
4. Drag your preset folder into the window, press Enter, then type `y`.

The first time, macOS says it can't verify the file. Click **Done**, then go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**. You only need to do this once.

If macOS asks to install command line developer tools, install them and run it again.

## Windows

1. Install Python from [python.org](https://www.python.org/downloads/), not the Microsoft Store.
2. Click the green **Code** button above, then **Download ZIP**.
3. Right-click the ZIP and choose **Properties**. If there's an **Unblock** box at the bottom, tick it and click **OK**. Then right-click the ZIP again and choose **Extract All**.
4. Quit your DAW.
5. Double-click **Import Presets (Windows)** in the extracted folder.
6. Drag your preset folder into the window, press Enter, then type `y`.

If Windows still warns you, click **Run** (or **More info**, then **Run anyway**).

## Good to know

- Presets are named `FOLDER - preset name`. Subfolders are included. Presets already in your library are skipped.
- Your preset list is backed up before every change. The tool shows where.
- Not affiliated with Cableguys.

## Other commands

In Terminal (on Windows, Command Prompt with `py -3` instead of `python3`):

```
python3 import_presets.py --preview path/to/presets   # show names, import nothing
python3 import_presets.py --undo                      # remove everything this tool imported
python3 import_presets.py --library path/to/library   # use this ShaperBox 3 library folder (the one with presets.db)
```
