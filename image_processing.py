from PIL import Image
import numpy as np


def load_grayscale_image(path: str) -> Image.Image:
    """
    Carica un'immagine e la converte in scala di grigi.
    """
    return Image.open(path).convert("L")


def posterize_image(
    image: Image.Image,
    thresholds: list[int],
    levels_count: int,
) -> Image.Image:
    """
    Posterizza un'immagine grayscale usando soglie personalizzate.

    Esempio con 3 valori:
    thresholds = [85, 170]
    output_levels = [0, 127, 255]
    """
    arr = np.array(image)

    thresholds = sorted(thresholds)

    output_levels = np.linspace(0, 255, levels_count).astype(np.uint8)

    # np.digitize assegna ogni pixel a una fascia tonale.
    # Esempio:
    # thresholds [85, 170]
    # 0-84     -> indice 0
    # 85-169   -> indice 1
    # 170-255  -> indice 2
    indices = np.digitize(arr, thresholds, right=False)

    result = output_levels[indices]

    return Image.fromarray(result.astype(np.uint8), mode="L")


def resize_for_preview(
    image: Image.Image,
    max_size: tuple[int, int] = (420, 420),
) -> Image.Image:
    """
    Ridimensiona solo per anteprima.
    Non modifica l'immagine originale salvabile.
    """
    preview = image.copy()
    preview.thumbnail(max_size)
    return preview


def calculate_histogram(image: Image.Image) -> list[int]:
    """
    Calcola l'istogramma dei valori grayscale.
    Restituisce 256 valori: uno per ogni luminosità da 0 a 255.
    """
    arr = np.array(image)

    # bincount è più diretto e veloce per immagini grayscale 0-255.
    hist = np.bincount(arr.ravel(), minlength=256)

    return hist.tolist()


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    """Convert normalized sRGB values to linear light.

    Args:
        c: NumPy array of sRGB channel values in the range [0, 1].

    Returns:
        A float64 array of linear-light channel values.
    """
    values = np.asarray(c, dtype=np.float64)
    return np.where(
        values <= 0.04045,
        values / 12.92,
        ((values + 0.055) / 1.055) ** 2.4,
    )


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    """Convert linear-light values to normalized sRGB.

    Args:
        c: NumPy array of linear-light channel values.

    Returns:
        A float64 array of encoded sRGB channel values.
    """
    values = np.asarray(c, dtype=np.float64)
    return np.where(
        values <= 0.0031308,
        values * 12.92,
        1.055 * np.maximum(values, 0.0) ** (1.0 / 2.4) - 0.055,
    )


def luminance(rgb_lin: np.ndarray) -> np.ndarray:
    """Calculate GIMP-weighted luminance from linear RGB values.

    Args:
        rgb_lin: Array whose final dimension contains linear R, G and B.

    Returns:
        Luminance values calculated with coefficients 0.222, 0.717 and 0.061.
    """
    values = np.asarray(rgb_lin, dtype=np.float64)
    if values.ndim == 0 or values.shape[-1] != 3:
        raise ValueError("Expected RGB values in the final array dimension.")
    return (
        0.222 * values[..., 0]
        + 0.717 * values[..., 1]
        + 0.061 * values[..., 2]
    )


def posterize_rgb(image: Image.Image, levels: int) -> Image.Image:
    """Posterize RGB channels independently using evenly spaced output levels.

    Args:
        image: Source image; it is converted to RGB, discarding alpha if present.
        levels: Number of output levels per channel, from 2 through 256.

    Returns:
        A posterized RGB image with the source dimensions.
    """
    if not 2 <= levels <= 256:
        raise ValueError("levels must be between 2 and 256.")

    arr = np.asarray(image.convert("RGB"), dtype=np.float64)
    step = 255.0 / (levels - 1)
    result = np.round(arr / step) * step
    result = np.clip(result, 0, 255).astype(np.uint8)
    return Image.fromarray(result)


def apply_luminance_blend(
    original: Image.Image,
    posterized: Image.Image,
) -> Image.Image:
    """Match original RGB color to posterized luminance in linear light.

    Args:
        original: Source colors; converted to RGB, discarding any alpha channel.
        posterized: Target luminance image, with the same dimensions as original.

    Returns:
        An RGB image with original chroma scaled toward posterized luminance.

    The ratio is capped at 10 to avoid extreme amplification. Output channels
    are clipped to the representable linear-light range [0, 1].
    """
    original_rgb = np.asarray(original.convert("RGB"), dtype=np.float64) / 255.0
    posterized_rgb = np.asarray(posterized.convert("RGB"), dtype=np.float64) / 255.0
    if original_rgb.shape != posterized_rgb.shape:
        raise ValueError("Images must have identical dimensions.")

    original_linear = srgb_to_linear(original_rgb)
    posterized_linear = srgb_to_linear(posterized_rgb)
    original_luminance = luminance(original_linear)
    posterized_luminance = luminance(posterized_linear)
    ratio = posterized_luminance / np.maximum(original_luminance, 1e-8)
    ratio = np.minimum(ratio, 10.0)

    blended_linear = np.clip(original_linear * ratio[..., np.newaxis], 0.0, 1.0)
    blended_srgb = linear_to_srgb(blended_linear)
    result = np.round(blended_srgb * 255.0).astype(np.uint8)
    return Image.fromarray(result)