from PIL import Image
import numpy as np


def generate_subject_mask(image: Image.Image) -> Image.Image:
    """Generate a binary foreground mask with MediaPipe Selfie Segmentation.

    The input is converted to RGB before inference. Confidence values at or
    above 0.5 are classified as foreground (255); all other pixels are 0.

    Args:
        image: Source image to segment.

    Returns:
        A single-channel ``L`` image matching the input dimensions.

    Raises:
        RuntimeError: If the legacy API is unavailable or no mask is returned.
    """
    import mediapipe as mp

    if not hasattr(mp, "solutions"):
        raise RuntimeError(
            "Selfie Segmentation richiede MediaPipe < 0.10.30."
        )

    image_rgb = np.asarray(image.convert("RGB"))
    with mp.solutions.selfie_segmentation.SelfieSegmentation(
        model_selection=1
    ) as segmenter:
        result = segmenter.process(image_rgb)

    if result.segmentation_mask is None:
        raise RuntimeError("MediaPipe non ha restituito una maschera.")

    binary_mask = (result.segmentation_mask >= 0.5).astype(np.uint8) * 255
    return Image.fromarray(binary_mask)