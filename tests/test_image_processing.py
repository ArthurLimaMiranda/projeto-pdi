import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pc_app"))

from image_processing import ProcessingSettings, process_frame  # noqa: E402


class ImageProcessingBaselineTest(unittest.TestCase):
    def test_baseline_returns_independent_copy(self):
        frame = np.arange(8 * 8 * 3, dtype=np.uint8).reshape((8, 8, 3))
        result = process_frame(frame)

        np.testing.assert_array_equal(result, frame)
        self.assertIsNot(result, frame)

    def test_none_is_preserved(self):
        self.assertIsNone(process_frame(None))

    def test_low_light_brightens_dark_frame_without_changing_input(self):
        frame = np.full((64, 64, 3), 12, dtype=np.uint8)
        result = process_frame(frame, ProcessingSettings(mode="baixa_luz"))

        self.assertEqual(result.shape, frame.shape)
        self.assertGreater(result.mean(), frame.mean())
        np.testing.assert_array_equal(frame, np.full_like(frame, 12))

    def test_median_removes_isolated_impulse(self):
        frame = np.full((32, 32, 3), 80, dtype=np.uint8)
        frame[16, 16] = 255
        result = process_frame(frame, ProcessingSettings(noise_mode="sal_pimenta"))

        np.testing.assert_array_equal(result[16, 16], [80, 80, 80])
        np.testing.assert_array_equal(frame[16, 16], [255, 255, 255])

    def test_all_modes_keep_displayable_shape_and_type(self):
        frame = np.arange(64 * 64 * 3, dtype=np.uint8).reshape((64, 64, 3))
        for mode in ("original", "baixa_luz", "contraste", "marcadores"):
            for noise in ("nenhum", "sal_pimenta", "listras", "estatico"):
                with self.subTest(mode=mode, noise=noise):
                    result = process_frame(frame, ProcessingSettings(mode=mode, noise_mode=noise))
                    self.assertEqual(result.shape, frame.shape)
                    self.assertEqual(result.dtype, np.uint8)
                    self.assertIsNot(result, frame)

    def test_adjustment_stays_in_valid_ranges(self):
        settings = ProcessingSettings(noise_mode="sal_pimenta", focus="noise")
        for _ in range(10):
            settings.adjust(1, 1)
        self.assertEqual(settings.median_kernel, 7)
        for _ in range(10):
            settings.adjust(1, -1)
        self.assertEqual(settings.median_kernel, 3)

    def test_periodic_filter_reduces_synthetic_stripes(self):
        height = width = 128
        clean = np.full((height, width, 3), 100, dtype=np.uint8)
        yy, xx = np.mgrid[:height, :width]
        stripes = 35 * np.sin(2 * np.pi * (0.08 * xx + 0.04 * yy))
        noisy = np.clip(clean.astype(np.float32) + stripes[..., None], 0, 255).astype(np.uint8)
        result = process_frame(noisy, ProcessingSettings(noise_mode="listras"))

        before = np.mean((noisy.astype(float) - clean) ** 2)
        after = np.mean((result.astype(float) - clean) ** 2)
        self.assertLess(after, before * 0.6)

    def test_static_filter_reduces_random_grain(self):
        clean = np.full((64, 64, 3), 110, dtype=np.uint8)
        rng = np.random.default_rng(7)
        noisy = np.clip(clean.astype(float) + rng.normal(0, 18, clean.shape), 0, 255).astype(np.uint8)
        result = process_frame(noisy, ProcessingSettings(noise_mode="estatico"))
        self.assertLess(np.mean((result.astype(float) - clean) ** 2),
                        np.mean((noisy.astype(float) - clean) ** 2))

    def test_dense_salt_and_pepper_uses_full_median(self):
        clean = np.full((80, 80, 3), 100, dtype=np.uint8)
        rng = np.random.default_rng(12)
        noisy = clean.copy()
        impulses = rng.random((80, 80)) < 0.17
        noisy[impulses] = rng.choice([0, 255], size=int(impulses.sum()))[:, None]
        result = process_frame(noisy, ProcessingSettings(noise_mode="sal_pimenta"))
        self.assertLess(np.mean(np.abs(result.astype(int) - clean.astype(int))), 2)

    def test_static_filter_leaves_clean_frame_unchanged(self):
        frame = np.full((64, 64, 3), 100, dtype=np.uint8)
        frame[20:40, 20:40] = 220
        result = process_frame(frame, ProcessingSettings(noise_mode="estatico"))
        np.testing.assert_array_equal(result, frame)

    def test_marker_analysis_returns_binary_mask_inside_roi(self):
        frame = np.full((100, 100, 3), 200, dtype=np.uint8)
        frame[48:55, 48:55] = (35, 35, 35)
        settings = ProcessingSettings(mode="marcadores", marker_roi=(0.3, 0.3, 0.8, 0.8))
        result = process_frame(frame, settings)
        self.assertEqual(result.shape, frame.shape)
        self.assertTrue(set(np.unique(result)).issubset({0, 255}))
        self.assertGreater(np.count_nonzero(result[44:58, 44:58]), 0)
        self.assertEqual(np.count_nonzero(result[:25]), 0)
        np.testing.assert_array_equal(frame[48:55, 48:55], np.full((7, 7, 3), 35, dtype=np.uint8))

    def test_marker_analysis_also_shows_body_edges(self):
        frame = np.full((100, 100, 3), 190, dtype=np.uint8)
        frame[30:75, 47:54] = 200
        frame[30:75, 47] = 60
        frame[30:75, 53] = 60
        frame[30:36, 47:54] = 35
        result = process_frame(frame, ProcessingSettings(
            mode="marcadores", marker_roi=(0.2, 0.2, 0.8, 0.8)
        ))
        self.assertGreater(np.count_nonzero(result[37:74, 45:56]), 0)

    def test_noise_and_low_light_are_combined(self):
        frame = np.full((64, 64, 3), 20, dtype=np.uint8)
        frame[32, 32] = 255
        settings = ProcessingSettings(mode="baixa_luz", noise_mode="sal_pimenta")
        result = process_frame(frame, settings)
        self.assertGreater(result.mean(), frame.mean())
        self.assertLess(abs(float(result[32, 32, 0]) - float(result[31, 32, 0])), 5)


if __name__ == "__main__":
    unittest.main()
