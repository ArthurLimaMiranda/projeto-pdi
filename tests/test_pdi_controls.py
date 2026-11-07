import sys
import unittest
from pathlib import Path

import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pc_app"))

from image_processing import ProcessingSettings  # noqa: E402
from pdi_controls import PDIControls  # noqa: E402


class PDIControlsTest(unittest.TestCase):
    def test_click_mode_drag_slider_and_toggle_mirror(self):
        controls = PDIControls()
        settings = ProcessingSettings()

        clicked = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=controls.mode_rects["baixa_luz"].center
        )
        self.assertTrue(controls.handle_event(clicked, settings))
        self.assertEqual(settings.mode, "baixa_luz")

        rail = controls._rail(controls.slider_rects[0])
        self.assertTrue(controls.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rail.midleft), settings
        ))
        self.assertAlmostEqual(settings.gamma, 0.25)
        self.assertTrue(controls.handle_event(
            pygame.event.Event(pygame.MOUSEMOTION, pos=rail.midright), settings
        ))
        self.assertAlmostEqual(settings.gamma, 1.50)
        self.assertTrue(controls.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=rail.midright), settings
        ))
        self.assertIsNone(controls.dragging)

        self.assertTrue(controls.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=controls.mirror_rect.center), settings
        ))
        self.assertTrue(settings.mirror)

    def test_second_slider_changes_active_mode_parameter(self):
        controls = PDIControls()
        settings = ProcessingSettings(mode="contraste")
        rail = controls._rail(controls.slider_rects[1])
        controls.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rail.midright), settings
        )
        self.assertEqual(settings.clahe_tiles, 12)

    def test_reset_button_restores_only_selected_mode(self):
        controls = PDIControls()
        settings = ProcessingSettings(
            mode="baixa_luz", gamma=0.85, clahe_clip=4.0,
            contrast_clip=5.0, clahe_tiles=12, mirror=True,
        )
        clicked = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=controls.reset_rect.center
        )
        self.assertTrue(controls.handle_event(clicked, settings))
        self.assertEqual(settings.gamma, 0.60)
        self.assertEqual(settings.clahe_clip, 2.0)
        self.assertEqual(settings.contrast_clip, 5.0)
        self.assertEqual(settings.clahe_tiles, 12)
        self.assertTrue(settings.mirror)

        settings.mode = "contraste"
        self.assertTrue(controls.handle_event(clicked, settings))
        self.assertEqual(settings.contrast_clip, 2.0)
        self.assertEqual(settings.clahe_tiles, 8)

    def test_noise_selection_does_not_replace_base_mode(self):
        controls = PDIControls()
        settings = ProcessingSettings(mode="baixa_luz", gamma=0.85)
        clicked = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=controls.noise_rects["listras"].center
        )
        self.assertTrue(controls.handle_event(clicked, settings))
        self.assertEqual(settings.mode, "baixa_luz")
        self.assertEqual(settings.noise_mode, "listras")
        self.assertEqual(settings.focus, "noise")
        settings.notch_radius = 8
        reset = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=controls.reset_rect.center
        )
        self.assertTrue(controls.handle_event(reset, settings))
        self.assertEqual(settings.notch_radius, 4)
        self.assertEqual(settings.gamma, 0.85)

    def test_marker_roi_drag_and_reset(self):
        controls = PDIControls()
        settings = ProcessingSettings(mode="marcadores")
        image_rect = pygame.Rect(300, 120, 400, 300)
        start = (340, 180)
        end = (620, 360)
        self.assertTrue(controls.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=start), settings, image_rect
        ))
        self.assertTrue(controls.handle_event(
            pygame.event.Event(pygame.MOUSEMOTION, pos=end, buttons=(1, 0, 0)), settings, image_rect
        ))
        self.assertTrue(controls.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=end), settings, image_rect
        ))
        self.assertEqual(settings.marker_roi, (0.1, 0.2, 0.8, 0.8))
        settings.focus = "base"
        settings.marker_threshold = 41
        controls.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=controls.reset_rect.center),
            settings, image_rect,
        )
        self.assertEqual(settings.marker_roi, ProcessingSettings().marker_roi)
        self.assertEqual(settings.marker_threshold, ProcessingSettings().marker_threshold)

    def test_marker_clicks_confirm_and_toggle_object_count(self):
        controls = PDIControls()
        settings = ProcessingSettings(mode="marcadores")
        original = pygame.Rect(300, 120, 400, 300)
        processed = pygame.Rect(790, 120, 400, 300)
        click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(990, 270))
        self.assertTrue(controls.handle_event(click, settings, original, processed))
        self.assertEqual(len(settings.marked_objects), 1)
        self.assertTrue(controls.handle_event(click, settings, original, processed))
        self.assertEqual(settings.marked_objects, [])
        outside = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(800, 130))
        self.assertFalse(controls.handle_event(outside, settings, original, processed))


if __name__ == "__main__":
    unittest.main()
