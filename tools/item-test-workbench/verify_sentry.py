#!/usr/bin/env python3
"""Check native sentry admission and turret replacement in an isolated scene."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def run(dll, *args):
    return subprocess.run([os.environ.get("DOTNET", "dotnet"), str(dll), *map(str, args)],
                          capture_output=True, text=True, timeout=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dll", type=Path, required=True)
    args = parser.parse_args()
    dll = args.native_dll.resolve()
    with tempfile.TemporaryDirectory(prefix="workbench-sentry-") as temp:
        root = Path(temp)
        fixtures = root / "fixtures"
        result = run(dll, "--write-fixtures", fixtures)
        if result.returncode:
            raise AssertionError(result.stderr)
        item = json.loads((fixtures / "synthetic-straight.json").read_text())
        entity = next(e for e in item["runtimeProgram"]["entities"] if e["id"] == "root")
        entity["nativeSentry"] = True
        entity["spawn"]["speedPxPerTick"] = 0
        entity["lifetimeTicks"] = 300
        entity["collision"]["pierce"] = -1
        item_path = root / "sentry.json"
        item_path.write_text(json.dumps(item))
        scenario = {
            "playerUpdate": "full", "ticks": 100, "seed": 1,
            "player": {"x": 640, "y": 640, "life": 100, "mana": 200, "manaCrystals": 9},
            "dummy": {"x": 1200, "y": 640, "life": 10000},
            "tiles": [{"tileX": 1, "tileY": 43, "width": 97, "height": 1}],
            "actions": [{"tick": 0, "kind": "primary"}, {"tick": 1, "kind": "release"},
                        {"tick": 50, "kind": "primary"}, {"tick": 51, "kind": "release"}],
            "assertions": [{"kind": "spawn_count", "value": 2}, {"kind": "no_nonfinite"}],
        }
        scenario_path = root / "scenario.json"
        output = root / "trace.json"
        scenario_path.write_text(json.dumps(scenario))
        result = run(dll, "--item", item_path, "--scenario", scenario_path, "--output", output)
        trace = json.loads(output.read_text())
        assert result.returncode == 0 and trace.get("status") == "passed", (result.stderr, trace.get("error"))
        events = [(frame["tick"], event) for frame in trace["snapshots"] for event in frame["events"]]
        spawns = [(tick, event["projectileId"]) for tick, event in events if event["kind"] == "spawn"]
        kills = [(tick, event["projectileId"]) for tick, event in events if event["kind"] == "kill"]
        assert len(spawns) == 2 and spawns[0][1] != spawns[1][1], spawns
        assert (50, spawns[0][1]) in kills, kills
        final = trace["snapshots"][-1]
        assert [p["id"] for p in final["projectiles"] if p["active"]] == [spawns[1][1]], final["projectiles"]
        scenario["playerUpdate"] = "item_check"
        scenario_path.write_text(json.dumps(scenario))
        result = run(dll, "--item", item_path, "--scenario", scenario_path, "--output", output)
        trace = json.loads(output.read_text())
        assert result.returncode == 2 and "Native sentry ownership/count maintenance" in trace.get("error", ""), trace
    print("Sentry full-player replacement and item-check refusal: PASS")


if __name__ == "__main__":
    main()
