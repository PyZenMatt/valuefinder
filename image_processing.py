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