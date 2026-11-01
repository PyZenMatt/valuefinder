import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from segmentation_tools import generate_subject_mask

try:
    import mediapipe as mp
except ImportError:
    mp = None

HAS_LEGACY_SELFIE_SEGMENTATION = (
    mp is not None and hasattr(mp, "solutions")
)


class SubjectSegmentationTests(unittest.TestCase):
    def test_mask_conversion_uses_rgb_and_confidence_threshold(self) -> None:
        """The wrapper requests model 1 and converts confidence to binary L."""
        captured = {}

        class FakeSegmenter:
            def __init__(self, model_selection: int) -> None:
                captured["model_selection"] = model_selection

            def __enter__(self) -> "FakeSegmenter":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def process(self, image: np.ndarray) -> SimpleNamespace:
                captured["image"] = image
                return SimpleNamespace(
                    segmentation_mask=np.array([[0.49, 0.5]], dtype=np.float32)
                )

        fake_mediapipe = SimpleNamespace(
            solutions=SimpleNamespace(
                selfie_segmentation=SimpleNamespace(
                    SelfieSegmentation=FakeSegmenter
                )
            )
        )
        image = Image.new("RGBA", (2, 1), (255, 255, 255, 128))

        with patch.dict(sys.modules, {"mediapipe": fake_mediapipe}):
            mask = generate_subject_mask(image)

        self.assertEqual(captured["model_selection"], 1)
        self.assertEqual(captured["image"].shape, (1, 2, 3))
        self.assertEqual(mask.mode, "L")
        self.assertEqual(np.asarray(mask).ravel().tolist(), [0, 255])

    @unittest.skipUnless(
        HAS_LEGACY_SELFIE_SEGMENTATION,
        "Installed MediaPipe does not include the legacy Selfie Segmentation API",
    )
    def test_synthetic_image_returns_same_size_grayscale_mask(self) -> None:
        """MediaPipe processes a small synthetic image into an L mask."""
        image = Image.new("RGB", (64, 64), "black")
        for x in range(20, 44):
            for y in range(10, 54):
                image.putpixel((x, y), (255, 255, 255))

        mask = generate_subject_mask(image)

        self.assertEqual(mask.size, image.size)
        self.assertEqual(mask.mode, "L")


if __name__ == "__main__":
    unittest.main()