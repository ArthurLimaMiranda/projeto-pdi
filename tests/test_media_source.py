import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pc_app"))

from media_source import MediaFileSource  # noqa: E402
from camera_viewer import CameraViewer  # noqa: E402


class CameraViewerTest(unittest.TestCase):
    def test_snapshot_invalidates_previous_frame_on_reconnect(self):
        with patch("camera_viewer.threading.Thread"):
            source = CameraViewer("http://camera.test")
        first = np.full((24, 32, 3), 10, dtype=np.uint8)
        second = np.full_like(first, 20)
        source._store_frame(first)
        frame, sequence, revision = source.read_frame_snapshot()
        np.testing.assert_array_equal(frame, first)
        self.assertEqual((sequence, revision), (1, 0))
        with self.assertLogs("camera_viewer", level="WARNING"):
            source._register_connection_error(ConnectionError("teste"))
        self.assertEqual(source.read_frame_snapshot(), (None, 1, 1))
        source._store_frame(second)
        frame, sequence, revision = source.read_frame_snapshot()
        np.testing.assert_array_equal(frame, second)
        self.assertEqual((sequence, revision), (2, 1))


class MediaFileSourceTest(unittest.TestCase):
    def test_image_source_returns_independent_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            expected = np.full((24, 32, 3), 120, dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(path), expected))

            source = MediaFileSource(path)
            first = source.read_frame()
            second = source.read_frame()

            np.testing.assert_array_equal(first, expected)
            np.testing.assert_array_equal(second, expected)
            self.assertIsNot(first, second)
            self.assertTrue(source.get_status()["opened"])
            source.release()

    def test_video_source_reads_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.avi"
            writer = cv2.VideoWriter(
                str(path),
                cv2.VideoWriter_fourcc(*"MJPG"),
                10.0,
                (32, 24),
            )
            self.assertTrue(writer.isOpened())
            for value in (30, 90, 150):
                writer.write(np.full((24, 32, 3), value, dtype=np.uint8))
            writer.release()

            source = MediaFileSource(path, loop=False)
            frame = source.read_frame()

            self.assertIsNotNone(frame)
            self.assertEqual(frame.shape, (24, 32, 3))
            self.assertTrue(source.get_status()["seekable"])
            self.assertAlmostEqual(source.get_status()["duration_sec"], 0.3, places=2)
            self.assertTrue(source.set_paused(True))
            _, sequence, revision = source.read_frame_snapshot()
            self.assertEqual(source.read_frame_snapshot()[1:], (sequence, revision))
            self.assertTrue(source.seek(0.2))
            self.assertTrue(source.get_status()["paused"])
            self.assertAlmostEqual(source.get_status()["position_sec"], 0.2, places=2)
            frame, new_sequence, new_revision = source.read_frame_snapshot()
            self.assertGreater(frame.mean(), 130)
            self.assertEqual(new_sequence, sequence + 1)
            self.assertEqual(new_revision, revision + 1)
            source.release()

    def test_missing_source_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            MediaFileSource("/arquivo/que/nao/existe.mp4")


if __name__ == "__main__":
    unittest.main()
