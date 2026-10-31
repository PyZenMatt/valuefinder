import unittest

import numpy as np
from PIL import Image

from image_processing import (
    apply_luminance_blend,
    luminance,
    posterize_image,
    posterize_rgb,
    srgb_to_linear,
)
from mask_tools import replace_background


class ColorPosterizationTests(unittest.TestCase):
    def test_posterize_rgb_uses_requested_number_of_levels(self) -> None:
        """Each channel uses exactly the requested quantization levels."""
        values = np.array([0, 85, 170, 255], dtype=np.uint8)
        pixels = np.repeat(values[np.newaxis, :, np.newaxis], 3, axis=2)
        image = Image.fromarray(pixels)

        result = posterize_rgb(image, levels=4)

        self.assertEqual(result.mode, "RGB")
        self.assertEqual(len(np.unique(np.asarray(result)[:, :, 0])), 4)

    def test_luminance_blend_handles_black_without_crashing(self) -> None:
        """Black source pixels remain finite when target luminance is nonzero."""
        original = Image.new("RGB", (1, 1), (0, 0, 0))
        posterized = Image.new("RGB", (1, 1), (255, 255, 255))

        result = apply_luminance_blend(original, posterized)

        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 0))

    def test_blended_luminance_matches_posterized_luminance(self) -> None:
        """The blended output reaches the target luminance when unclipped."""
        original = Image.new("RGB", (1, 1), (80, 70, 60))
        posterized = Image.new("RGB", (1, 1), (40, 35, 30))

        result = apply_luminance_blend(original, posterized)
        result_linear = srgb_to_linear(np.asarray(result, dtype=np.float64) / 255.0)
        target_linear = srgb_to_linear(
            np.asarray(posterized, dtype=np.float64) / 255.0
        )

        result_luminance = float(luminance(result_linear)[0, 0])
        target_luminance = float(luminance(target_linear)[0, 0])
        self.assertAlmostEqual(result_luminance, target_luminance, delta=0.005)

    def test_grayscale_posterization_behavior_is_unchanged(self) -> None:
        """Existing grayscale threshold behavior, including equality, is stable."""
        image = Image.frombytes("L", (4, 1), bytes([0, 127, 128, 255]))

        result = posterize_image(image, thresholds=[127], levels_count=2)

        self.assertEqual(np.asarray(result).ravel().tolist(), [0, 255, 255, 255])

    def test_background_replacement_preserves_rgb(self) -> None:
        """RGB subjects remain colored while the exterior uses gray fill."""
        image = Image.new("RGB", (2, 1))
        image.putdata([(20, 40, 60), (100, 120, 140)])
        mask = Image.new("L", (2, 1))
        mask.putdata([255, 0])

        result = replace_background(image, mask, background_value=200)

        self.assertEqual(result.mode, "RGB")
        self.assertEqual(
            np.asarray(result).reshape(-1, 3).tolist(),
            [[20, 40, 60], [200, 200, 200]],
        )

    def test_background_replacement_keeps_grayscale_behavior(self) -> None:
        """Grayscale inputs still produce the established grayscale result."""
        image = Image.new("L", (2, 1))
        image.putdata([35, 90])
        mask = Image.new("L", (2, 1))
        mask.putdata([255, 0])

        result = replace_background(image, mask, background_value=200)

        self.assertEqual(result.mode, "L")
        self.assertEqual(np.asarray(result).ravel().tolist(), [35, 200])


if __name__ == "__main__":
    unittest.main()