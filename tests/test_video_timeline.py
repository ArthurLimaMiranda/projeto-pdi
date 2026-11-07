import sys
import unittest
from pathlib import Path

import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pc_app"))

from video_timeline import VideoTimeline  # noqa: E402


class FakeVideoSource:
    def __init__(self):
        self.position = 0.0
        self.paused = False

    def get_status(self):
        return {
            "seekable": True, "duration_sec": 10.0,
            "position_sec": self.position, "paused": self.paused,
        }

    def set_paused(self, paused):
        self.paused = paused

    def seek(self, position):
        self.position = position
        return True


class VideoTimelineTest(unittest.TestCase):
    def test_mouse_seek_and_pause_button(self):
        timeline = VideoTimeline()
        source = FakeVideoSource()
        x = timeline.rail.left + round(timeline.rail.width * 0.75)
        y = timeline.rail.centery

        self.assertTrue(timeline.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y)), source
        ))
        self.assertTrue(source.paused)
        self.assertTrue(timeline.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(x, y)), source
        ))
        self.assertAlmostEqual(source.position, 7.5)
        self.assertFalse(source.paused)

        self.assertTrue(timeline.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=timeline.pause_rect.center), source
        ))
        self.assertTrue(source.paused)


if __name__ == "__main__":
    unittest.main()
