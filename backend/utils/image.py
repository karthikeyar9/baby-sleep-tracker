import cv2
import numpy as np


def maintain_aspect_ratio_resize(image, width=None, height=None, inter=cv2.INTER_AREA):
    """Resize image while maintaining aspect ratio.

    Returns (resized_image, new_dimensions).
    """
    dim = None
    (h, w) = image.shape[:2]

    if width is None and height is None:
        return image, None

    if width is None:
        r = height / float(h)
        dim = (int(w * r), height)
    else:
        r = width / float(w)
        dim = (width, int(h * r))

    return cv2.resize(image, dim, interpolation=inter), dim


def gamma_correction(image, gamma):
    """Apply gamma correction to an image."""
    inv_gamma = 1.0 / gamma
    table = [((i / 255.0) ** inv_gamma) * 255 for i in range(256)]
    table = np.array(table, np.uint8)
    return cv2.LUT(image, table)
