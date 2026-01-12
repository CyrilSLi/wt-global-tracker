import json, subprocess
with open("stop_selection_freq.json") as f:
    subprocess.run(["wl-copy", "\n".join(f"{j}\t{i}" for j, i in enumerate(json.load(f).values()))])