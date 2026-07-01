import tempfile
import unittest
from pathlib import Path

from prismax.manifest import build_manifest_payload, manifest_placeholder
from prismax.scanner import episode_keys, scan_folder, validate_mcap_mp4


class UploadHelperTests(unittest.TestCase):
    def test_scan_validate_and_build_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "1").mkdir()
            (root / "1.mcap").write_bytes(b"mcap")
            (root / "1" / "left.mp4").write_bytes(b"left")
            (root / "1" / "right.mp4").write_bytes(b"right")
            (root / "1" / "high.mp4").write_bytes(b"env")
            (root / "1" / "_MANIFEST.json").write_text("ignored")

            files = scan_folder(root)

            self.assertEqual(
                sorted(item.relative_path for item in files),
                ["1.mcap", "1/high.mp4", "1/left.mp4", "1/right.mp4"],
            )
            self.assertEqual(validate_mcap_mp4(files), [])
            self.assertEqual(episode_keys(files), ["1"])
            self.assertEqual(
                manifest_placeholder("1"),
                {
                    "relative_path": "1/_MANIFEST.json",
                    "size_bytes": None,
                    "content_type": "application/json",
                },
            )

            manifest = build_manifest_payload(
                episode_key="1",
                upload_id=123,
                machine_id="machine-1",
                task_id=9,
                files=files,
            )

            self.assertEqual(manifest["manifest_version"], 1)
            self.assertEqual(manifest["upload_id"], 123)
            self.assertEqual(manifest["episode_key"], "1")
            self.assertEqual(len(manifest["files"]), 4)


if __name__ == "__main__":
    unittest.main()
