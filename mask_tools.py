from PIL import Image, ImageDraw
import numpy as np


def create_polygon_mask(
    image_size: tuple[int, int],
    points: list[tuple[int, int]],
) -> Image.Image:
    """
    Crea una maschera L:
    255 = soggetto
    0 = sfondo
    """
    mask = Image.new("L", image_size, 0)

    if len(points) >= 3:
        draw = ImageDraw.Draw(mask)
        draw.polygon(points, fill=255)

    return mask


def replace_background(
    image: Image.Image,
    mask: Image.Image,
    background_value: int,
) -> Image.Image:
    """Replace masked-out pixels with a solid grayscale background.

    RGB input remains RGB for color-mode previews and exports; other input
    modes retain the existing grayscale behavior.
    """
    mask_arr = np.asarray(mask.convert("L"))

    if image.mode == "RGB":
        image_arr = np.asarray(image)
        bg = np.full_like(image_arr, background_value, dtype=np.uint8)
        result = np.where(mask_arr[..., np.newaxis] > 0, image_arr, bg)
        return Image.fromarray(result.astype(np.uint8))

    image_arr = np.asarray(image.convert("L"))

    bg = np.full_like(image_arr, background_value, dtype=np.uint8)
    result = np.where(mask_arr > 0, image_arr, bg)

    return Image.fromarray(result.astype(np.uint8), mode="L")


def scale_points(
    points: list[tuple[int, int]],
    from_size: tuple[int, int],
    to_size: tuple[int, int],
) -> list[tuple[int, int]]:
    """
    Scala punti dalla preview alla full-res.
    """
    from_w, from_h = from_size
    to_w, to_h = to_size

    scale_x = to_w / from_w
    scale_y = to_h / from_h

    return [
        (int(x * scale_x), int(y * scale_y))
        for x, y in points
    ]