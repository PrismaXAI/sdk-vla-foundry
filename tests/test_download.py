import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from prismax import cli
from prismax.client import PrismaXClient
from prismax.download import create_download_session, download
from prismax.errors import PrismaxAuthError
from prismax.upload import status


download_module = importlib.import_module("prismax.download")


def _session_payload():
    return {
        "download_id": 91,
        "package_id": "pkg_test",
        "samples": [
            {
                "upload_id": 7,
                "episode_id": 8,
                "assets": {
                    "mcap": {
                        "relative_path": "episode_1.mcap",
                        "url": "https://cdn.test/episode_1.mcap",
                        "auth": {"cookie_header": "cookie-mcap"},
                    },
                    "env": {
                        "relative_path": "episode_1/high.mp4",
                        "url": "https://cdn.test/high.mp4",
                        "auth": {"cookie_header": "cookie-high"},
                    },
                    "left": {
                        "relative_path": "episode_1/left.mp4",
                        "url": "https://cdn.test/left.mp4",
                        "auth": {"cookie_header": "cookie-left"},
                    },
                    "right": {
                        "relative_path": "episode_1/right.mp4",
                        "url": "https://cdn.test/right.mp4",
                        "auth": {"cookie_header": "cookie-right"},
                    },
                },
                "additional_videos": [
                    {
                        "relative_path": "episode_1/wrist.mp4",
                        "url": "https://cdn.test/wrist.mp4",
                        "auth": {"cookie_header": "cookie-wrist"},
                    }
                ],
            }
        ],
    }


class DownloadTests(unittest.TestCase):
    def test_download_uses_download_key_environment_variable(self):
        response = Mock()
        response.ok = True
        response.json.return_value = {"success": True, "data": _session_payload()}

        with patch.dict(
            os.environ,
            {
                "PRISMAX_UPLOAD_API_KEY": "pxu_upload",
                "PRISMAX_DOWNLOAD_API_KEY": "pxa_download",
            },
            clear=True,
        ), patch("prismax.client.requests.request", return_value=response) as request_mock:
            create_download_session("pkg_test", base_url="https://example.test")

        self.assertEqual(
            request_mock.call_args.kwargs["headers"]["X-API-Key"],
            "pxa_download",
        )

    def test_upload_uses_upload_key_environment_variable(self):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "success": True,
            "data": {"upload_id": 12, "status": "UPLOADING"},
        }

        with patch.dict(
            os.environ,
            {
                "PRISMAX_UPLOAD_API_KEY": "pxu_upload",
                "PRISMAX_DOWNLOAD_API_KEY": "pxa_download",
            },
            clear=True,
        ), patch("prismax.client.requests.request", return_value=response) as request_mock:
            status(12, base_url="https://example.test")

        self.assertEqual(
            request_mock.call_args.kwargs["headers"]["X-API-Key"],
            "pxu_upload",
        )

    def test_download_rejects_upload_key(self):
        with self.assertRaises(PrismaxAuthError) as ctx:
            create_download_session(
                "pkg_test",
                api_key="pxu_wrong_key",
                base_url="https://example.test",
            )

        self.assertIn("pxa_", str(ctx.exception))

    def test_upload_rejects_download_key(self):
        with self.assertRaises(PrismaxAuthError) as ctx:
            status(
                12,
                api_key="pxa_wrong_key",
                base_url="https://example.test",
            )

        self.assertIn("pxu_", str(ctx.exception))

    def test_download_includes_additional_videos_and_asset_cookies(self):
        client = Mock()
        client.create_download_session.return_value = _session_payload()

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            download_module, "PrismaXClient", return_value=client
        ):
            result = download(
                "pkg_test",
                tmp,
                api_key="pxa_download",
                base_url="https://example.test",
                progress=False,
            )

        items = client.download_files.call_args.args[0]
        self.assertEqual(result["file_count"], 5)
        self.assertEqual(
            [item["relative_path"] for item in items],
            [
                "episode_1.mcap",
                "episode_1/high.mp4",
                "episode_1/left.mp4",
                "episode_1/right.mp4",
                "episode_1/wrist.mp4",
            ],
        )
        self.assertEqual(
            [item["cookie_header"] for item in items],
            [
                "cookie-mcap",
                "cookie-high",
                "cookie-left",
                "cookie-right",
                "cookie-wrist",
            ],
        )

    def test_client_sends_cookie_and_writes_download(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b"robot", b"data"]

        with tempfile.TemporaryDirectory() as tmp, patch(
            "prismax.client.requests.get", return_value=response
        ) as get_mock:
            destination = Path(tmp) / "episode.mcap"
            client = PrismaXClient(
                api_key="pxa_download",
                base_url="https://example.test",
            )
            client.download_file_from_cdn(
                url="https://cdn.test/episode.mcap",
                cookie_header="asset-cookie",
                destination=destination,
            )

            self.assertEqual(destination.read_bytes(), b"robotdata")

        self.assertEqual(
            get_mock.call_args.kwargs["headers"],
            {"Cookie": "asset-cookie"},
        )

    def test_cli_download_prints_summary(self):
        result = {
            "download_id": 91,
            "package_id": "pkg_test",
            "episode_count": 1,
            "file_count": 5,
            "output": "./dataset",
        }
        with patch("prismax.cli.download", return_value=result) as download_mock, patch(
            "builtins.print"
        ) as print_mock:
            exit_code = cli.main(
                ["download", "pkg_test", "--output", "./dataset", "--no-progress"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(download_mock.call_args.args[:2], ("pkg_test", "./dataset"))
        printed = "\n".join(call.args[0] for call in print_mock.call_args_list)
        self.assertIn("Download ID: 91", printed)
        self.assertIn("Files: 5", printed)


if __name__ == "__main__":
    unittest.main()
