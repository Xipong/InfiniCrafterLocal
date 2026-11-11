"""Synthetic GIF timing regressions, not browser speed or native gameplay tests."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from python import campaign, native_review, probe
import workbench as w

try:
    from PIL import Image, ImageSequence
except ImportError:
    Image = None


def sequence(root, count, identical=False):
    """Distinct real PNGs prevent GIF coalescing from concealing short delays."""
    (root / "native-frames").mkdir()
    frames = []
    for tick in range(count):
        path = root / f"native-frames/{tick}.png"
        color = (0, 0, 0, 255) if identical else (tick % 256, tick // 256, tick * 37 % 256, 255)
        Image.new("RGBA", (160, 128), color).save(path)
        frames.append({"tick": tick, "path": str(path.relative_to(root)), "width": 160, "height": 128,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "scene": {"player": {"screenLeft": 30, "screenRight": 40, "screenTop": 50, "screenBottom": 70}}})
    trace = {"status": "passed", "timeline": {"completedTicks": count},
             "snapshots": [{"tick": tick, "player": {"direction": 1}, "events": []} for tick in range(count)],
             "nativeRender": {"backend": "original_mod_draw_layers", "itemArtworkRendered": False,
                              "projectileArtworkRendered": False, "worldRendered": False, "frames": frames}}
    path = root / "native.json"
    path.write_text(json.dumps(trace))
    return trace, path


def decoded_delays(path):
    with Image.open(path) as gif:
        return [frame.info["duration"] for frame in ImageSequence.Iterator(gif)]


@unittest.skipIf(Image is None, "Optional Pillow is not installed")
class GifTimingTests(unittest.TestCase):
    def test_default_decoded_gifs_keep_native_duration_and_viewer_safe_delays(self):
        for count in (3, 4, 5, 6, 120, 121, 180, 240, 600):
            with self.subTest(ticks=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                trace, path = sequence(root, count)
                original = copy.deepcopy(trace)
                trace_bytes = path.read_bytes()
                result = native_review.export_native_review(trace, path, root / "review", gif=True)
                metadata = json.loads((root / "review/native-review.json").read_text())
                timing = metadata["gif"]
                self.assertEqual(timing["stride"], 2)
                self.assertEqual(timing["sourceTicks"][0], 0)
                self.assertEqual(timing["sourceTicks"][-1], count - 1)
                expected_ticks = list(range(0, count, 2))
                if count % 2 == 0:
                    expected_ticks[-1] = count - 1
                self.assertEqual(timing["sourceTicks"], expected_ticks)
                self.assertEqual(timing["omittedFrames"], count - len(expected_ticks))
                self.assertEqual(timing["frameDurationsMs"][-1], 800)
                self.assertTrue(all(ms >= 30 and ms % 10 == 0 for ms in timing["frameDurationsMs"][:-1]))
                self.assertEqual(sum(timing["frameDurationsMs"]), round((count - 1) * 100 / 60) * 10 + 800)
                elapsed = 0
                for tick, delay in zip(timing["sourceTicks"], timing["frameDurationsMs"]):
                    self.assertEqual(elapsed, round(tick * 100 / 60) * 10)
                    elapsed += delay
                for key in ("nativeGif", "nativeCloseGif"):
                    self.assertEqual(decoded_delays(result[key]), timing["frameDurationsMs"])
                self.assertEqual(trace, original)
                self.assertEqual(path.read_bytes(), trace_bytes)
                self.assertEqual(len(metadata["frames"]), count)
                self.assertEqual(metadata["nativeRendering"], trace["nativeRender"])
                page = (root / "review/native.html").read_text()
                embedded = json.loads(page.split("const data=", 1)[1].split(",frames=data.frames", 1)[0])
                self.assertEqual(embedded["states"], trace["snapshots"])
                self.assertEqual(len(embedded["frames"]), count)
                for frame in metadata["frames"]:
                    raw = (root / "review" / frame["path"]).read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), frame["sha256"])

    def test_explicit_sampled_strides_omit_only_short_penultimate_tail(self):
        for stride, ticks in ((2, [0, 2, 5]), (7, [0, 7, 15])):
            with self.subTest(stride=stride), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                trace, path = sequence(root, ticks[-1] + 1)
                result = native_review.export_native_review(trace, path, root / "review", gif=True, gif_stride=stride)
                timing = json.loads((root / "review/native-review.json").read_text())["gif"]
                self.assertEqual(timing["stride"], stride)
                self.assertEqual(timing["sourceTicks"], ticks)
                self.assertTrue(all(ms >= 30 for ms in decoded_delays(result["nativeGif"])))
                self.assertEqual(sum(decoded_delays(result["nativeGif"])), round(ticks[-1] * 100 / 60) * 10 + 800)

    def test_coalesced_identical_frames_preserve_encoded_total_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace, path = sequence(root, 240, identical=True)
            result = native_review.export_native_review(trace, path, root / "review", gif=True)
            for key in ("nativeGif", "nativeCloseGif"):
                self.assertEqual(decoded_delays(result[key]), [4780])

    def test_explicit_stride_one_preserves_every_tick_and_centisecond_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace, path = sequence(root, 121)
            result = native_review.export_native_review(trace, path, root / "review", gif=True, gif_stride=1)
            timing = json.loads((root / "review/native-review.json").read_text())["gif"]
            self.assertEqual(timing["stride"], 1)
            self.assertEqual(timing["sourceTicks"], list(range(121)))
            self.assertEqual(set(timing["frameDurationsMs"][:-1]), {10, 20})
            self.assertEqual(sum(decoded_delays(result["nativeGif"])), 2800)

    def test_one_and_two_tick_clips_keep_exact_source_timing(self):
        for count in (1, 2):
            with self.subTest(ticks=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                trace, path = sequence(root, count)
                result = native_review.export_native_review(trace, path, root / "review", gif=True)
                expected = [800] if count == 1 else [20, 800]
                self.assertEqual(decoded_delays(result["nativeGif"]), expected)


class GifEntryPointTests(unittest.TestCase):
    def test_run_and_native_review_cli_defaults_and_explicit_stride(self):
        for command in ("run", "native-review"):
            for explicit in (None, 1, 7):
                with self.subTest(command=command, stride=explicit):
                    args = ["workbench", command]
                    if command == "run":
                        args += ["--item", "item.json", "--scenario", "scene.json", "--review", "native"]
                    else:
                        args += ["native.json"]
                    args += ["--out", "review", "--gif"]
                    if explicit is not None:
                        args += ["--gif-stride", str(explicit)]
                    with patch.object(sys, "argv", args), patch.object(w, "execute_run", return_value={"exitCode": 0}) as run, \
                            patch.object(w, "read_native_json", return_value={}), patch.object(w, "validate_trace", return_value={}), \
                            patch.object(native_review, "export_native_review", return_value={}) as export, \
                            patch("builtins.print"):
                        self.assertEqual(w.main(), 0)
                    stride = run.call_args.args[0].gif_stride if command == "run" else export.call_args.args[4]
                    self.assertEqual(stride, explicit if explicit is not None else 2)

    def test_probe_defaults_to_two_and_retains_budget_and_explicit_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            parser = argparse.ArgumentParser()
            probe.add_parser(parser.add_subparsers(dest="command", required=True))
            base = ["probe", "--vanilla-item", "Clentaminator", "--vanilla-assets", directory, "--gif"]
            for extra, expected in ((["--ticks", "30"], 2), (["--ticks", "30", "--gif-stride", "1"], 1),
                                    (["--ticks", "30", "--gif-stride", "7"], 7), (["--ticks", "600"], 4)):
                with self.subTest(extra=extra):
                    plan = probe.plan_probe(parser.parse_args(base + extra))
                    self.assertEqual(plan["cases"][0]["gifStride"], expected)
                    self.assertEqual(plan["scenes"]["001-primary"]["ticks"], int(extra[1]))

    def test_suite_default_and_explicit_stride_reach_run_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scene.json").write_text("{}")
            cases = [{"name": name, "vanillaItem": "WoodenBow", "scenario": "scene.json", "gif": True,
                      "review": "native", "expect": {"status": "passed"}, **fields}
                     for name, fields in (("default", {}), ("all", {"gifStride": 1}), ("sparse", {"gifStride": 7}))]
            manifest = root / "suite.json"
            manifest.write_text(json.dumps({"schemaVersion": 1, "cases": cases}))
            with patch.object(w, "native_executable"), \
                    patch.object(campaign.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run, \
                    patch.object(campaign, "report", side_effect=ValueError("synthetic command-only test")):
                campaign.run_suite(manifest, root / "out", no_build=True)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([command[command.index("--gif-stride") + 1] for command in commands], ["2", "1", "7"])


if __name__ == "__main__":
    unittest.main()
