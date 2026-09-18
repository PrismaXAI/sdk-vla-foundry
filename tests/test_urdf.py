import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from prismax.client import PrismaXClient
from prismax.data_upload import DataUpload
from prismax.errors import PrismaxApiError, PrismaxValidationError
from prismax.manifest import build_manifest_payload
from prismax.scanner import scan_folder, validate_mcap_mp4


def flat_spec(keys):
    return {
        "scenario": "Test scenario",
        "robot": {"serial_number": "test-robot"},
        "episode_set": {
            "mode": "templated", "episode_keys": keys,
            "file_layout": {
                "mcap": {"source_path": "{episode_key}/telemetry.webui.mcap"},
                "primary_videos": {
                    "env": {"source_path": "{episode_key}/cam_high.mp4"},
                    "left": {"source_path": "{episode_key}/cam_left_wrist.mp4"},
                    "right": {"source_path": "{episode_key}/cam_right_wrist.mp4"},
                },
                "urdf": {"source_path": "{episode_key}/robot.urdf"},
            },
        },
    }


class UrdfTests(unittest.TestCase):
    def test_flat_directory_mapping_in_explicit_and_templated_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "30361").mkdir()
            names = ["telemetry.webui.mcap", "cam_high.mp4", "cam_left_wrist.mp4",
                     "cam_right_wrist.mp4", "robot.urdf"]
            for name in names:
                (root / "30361" / name).write_bytes(b"test")
            spec = flat_spec(["30361"])
            layout = spec["episode_set"]["file_layout"]
            for mode in ("templated", "explicit"):
                with self.subTest(mode=mode):
                    if mode == "explicit":
                        assets = {
                            "mcap": {"source_path": "30361/telemetry.webui.mcap"},
                            "primary_videos": {
                                slot: {"source_path": item["source_path"].format(episode_key="30361")}
                                for slot, item in layout["primary_videos"].items()
                            },
                            "urdf": {"source_path": "30361/robot.urdf"},
                        }
                        spec["episode_set"] = {"mode": mode, "episodes": [
                            {"episode_key": "30361", "assets": assets},
                        ]}
                    data = DataUpload.from_dict(spec, base_path=root)
                    self.assertEqual(validate_mcap_mp4(data.files), [])
                    self.assertEqual({f.relative_path for f in data.files}, {
                        "30361.mcap", "30361/high.mp4", "30361/left.mp4",
                        "30361/right.mp4", "30361/robot.urdf",
                    })
                    urdf = next(f for f in data.files if f.relative_path.endswith(".urdf"))
                    self.assertEqual(urdf.path, (root / "30361/robot.urdf").resolve())
                    manifest = build_manifest_payload(episode_key="30361", upload_id=1,
                        machine_id="robot", task_id=2, files=data.files)
                    self.assertEqual(len(manifest["files"]), 4)
                    self.assertFalse(any(f["relative_path"].endswith(".urdf") for f in manifest["files"]))

    def test_standard_folder_accepts_one_urdf_per_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            (root / "a.mcap").write_bytes(b"test")
            for name in ("high.mp4", "left.mp4", "right.mp4", "robot.urdf"):
                (root / "a" / name).write_bytes(b"test")
            self.assertEqual(validate_mcap_mp4(scan_folder(root)), [])
            for invalid in ("a/second.urdf", "robot.urdf", "a/uppercase.URDF", "unknown/robot.urdf"):
                with self.subTest(invalid=invalid):
                    path = root / invalid
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(b"test")
                    self.assertTrue(validate_mcap_mp4(scan_folder(root)))
                    path.unlink()

    def test_shared_urdf_can_map_to_multiple_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = flat_spec(["a", "b"])
            for key in ("a", "b"):
                (root / key).mkdir()
                for name in ("telemetry.webui.mcap", "cam_high.mp4", "cam_left_wrist.mp4", "cam_right_wrist.mp4"):
                    (root / key / name).write_bytes(b"test")
            (root / "shared.urdf").write_bytes(b"robot")
            spec["episode_set"]["file_layout"]["urdf"] = {"source_path": "shared.urdf"}
            data = DataUpload.from_dict(spec, base_path=root)
            self.assertEqual([f.relative_path for f in data.files if f.relative_path.endswith(".urdf")],
                             ["a/shared.urdf", "b/shared.urdf"])
            spec["episode_set"]["file_layout"]["urdf"] = {"source_path": "missing.urdf"}
            with self.assertRaises(PrismaxValidationError):
                DataUpload.from_dict(spec, base_path=root)

    def test_failed_urdf_transfer_does_not_abort_required_files(self):
        client = PrismaXClient(require_api_key=False)
        urdf = {"signed_url": "https://signed.test", "path": "robot.urdf",
                "relative_path": "a/robot.urdf", "content_type": "application/xml"}
        video = {**urdf, "path": "high.mp4", "relative_path": "a/high.mp4"}
        callback = Mock()
        def transfer(**kwargs):
            if kwargs["relative_path"].endswith(".urdf"):
                raise PrismaxApiError("network failure")
        with patch.object(client, "upload_file_to_signed_url", side_effect=transfer), self.assertLogs("prismax.client"):
            client.upload_files([urdf, video], on_file_complete=callback)
        self.assertEqual(callback.call_count, 2)
        callback.assert_any_call({**urdf, "optional_upload_failed": True})
        with patch.object(client, "upload_file_to_signed_url", side_effect=PrismaxApiError("failure")):
            with self.assertRaises(PrismaxApiError):
                client.upload_files([video])

    def test_download_same_urdf_name_from_different_uploads(self):
        module = importlib.import_module("prismax.download")
        session = {"samples": [
            {"upload_id": upload, "episode_id": episode, "assets": {"urdf": {
                "relative_path": f"{episode}/robot.urdf", "url": f"https://cdn.test/raw/{upload}/robot.urdf",
                "auth": {"cookie_header": f"cookie-{episode}"},
            }}} for upload, episode in ((7, 8), (9, 10))
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            items = module._download_items(session, Path(tmp))
            self.assertEqual([item["destination"] for item in items],
                             [Path(tmp) / "8/robot.urdf", Path(tmp) / "10/robot.urdf"])
            self.assertEqual([item["cookie_header"] for item in items], ["cookie-8", "cookie-10"])
