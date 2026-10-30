import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from validators import validate_project
from errors import ValidationError

root = os.path.join(os.path.dirname(__file__), "..", "samples")
for f in sorted(glob.glob(os.path.join(root, "*project*.json")) + glob.glob(os.path.join(root, "scenario_*.json"))):
    try:
        validate_project(json.load(open(f, encoding="utf-8")))
        print("OK  ", os.path.basename(f))
    except (ValidationError, json.JSONDecodeError) as e:
        print("FAIL", os.path.basename(f), "->", e)
