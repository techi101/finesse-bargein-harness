"""Copy the real benchmark output into the demo site.

    python demo/build_data.py

Reads results/results.json (written by bench.py) and writes demo/data.json. Nothing is
computed or rounded here except a source note; the page reads every number from data.json.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = ROOT / "results" / "results.json"
res = json.loads(src.read_text())
res["source"] = "results/results.json (written by bench.py)"
(ROOT / "demo" / "data.json").write_text(json.dumps(res, indent=2))
print("wrote demo/data.json from", src.relative_to(ROOT))
