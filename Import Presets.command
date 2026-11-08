#!/bin/bash
# Double-click in Finder: asks for a preset folder, then runs import_presets.py on it.
cd "$(dirname "$0")" || exit 1
clear
echo "ShaperBox Preset Importer"
echo
echo "Quit your DAW first."
echo
echo "Drag your preset folder into this window, then press Enter:"
read -r line

# Terminal escapes dragged paths ("My\ Presets"); split them back into plain paths.
folders=()
while IFS= read -r -d '' p; do
    folders+=("$p")
done < <(python3 -c '
import shlex, sys
try:
    paths = shlex.split(sys.argv[1])
except ValueError:
    paths = [sys.argv[1].strip()]
sys.stdout.write("".join(p + "\0" for p in paths))
' "$line")

echo
if [ ${#folders[@]} -eq 0 ]; then
    echo "No folder given. Close this window and try again."
    exit 1
fi
python3 import_presets.py "${folders[@]}"
