import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


visual = load("agentlab-visual-evidence")
stage = load("agentlab-visual-evidence-stage")


class VisualEvidenceTests(unittest.TestCase):
    def test_multiple_frames_are_bound_and_originals_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frames = []
            for i in range(3):
                path = root / f"{i}.png"
                Image.new("RGB", (160, 200), (i * 70, 40, 100)).save(path)
                frames.append({"stepId": str(i), "caseId": "case", "operationId": "op",
                               "observationRef": str(i), "path": path.name,
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            before = [(root / row["path"]).read_bytes() for row in frames]
            manifest = root / "input.json"
            manifest.write_text(json.dumps({"frames": frames}))
            index = visual.encode(manifest, root / "output", width=160)
            self.assertEqual([r["frameIndex"] for r in index["frames"]], [0, 1, 2])
            self.assertEqual(visual.verify(root / "output/index.json")["frames"], 3)
            self.assertEqual(before, [(root / row["path"]).read_bytes() for row in frames])
            with self.assertRaisesRegex(ValueError, "exists"):
                visual.encode(manifest, root / "output")
            (root / "output/sequence.avif").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "integrity"):
                visual.verify(root / "output/index.json")

    def test_source_and_path_checks_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                visual.relative(root, "../outside")
            path = root / "frame.png"
            Image.new("RGB", (64, 64)).save(path)
            manifest = root / "input.json"
            manifest.write_text(json.dumps({"frames": [{"stepId": "1", "caseId": "c",
                "operationId": "o", "observationRef": "r", "path": path.name, "sha256": "0" * 64}]}))
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                visual.encode(manifest, root / "output")
            self.assertFalse((root / "output").exists())

    def test_staging_rejects_unverified_wheel(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wheel = root / "pillow-cp312-cp312-manylinux_2_28_x86_64.whl"
            wheel.write_bytes(b"not a wheel")
            with self.assertRaisesRegex(ValueError, "digest"):
                stage.stage(wheel, "0" * 64, root / "out", ROOT / "scripts/agentlab-visual-evidence.py", "linux-x64")
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
