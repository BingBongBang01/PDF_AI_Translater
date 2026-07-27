import cv2
import numpy as np


def clean_manga_text_region(cropped_img: np.ndarray) -> np.ndarray:
    if len(cropped_img.shape) == 3:
        gray = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = cropped_img.copy()

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )

    contours, _ = cv2.findContours(
        binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = gray.shape[:2]
    img_area = h * w

    char_mask = np.zeros((h, w), dtype=np.uint8)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue

        bx, by, bw, bh = cv2.boundingRect(cnt)
        area_to_perimeter = area / perimeter

        is_giant_bubble = (
            area > 0.4 * img_area
            or (bw > 0.85 * w and bh > 0.85 * h)
            or (area_to_perimeter > (min(h, w) / 8.0) and area > 0.15 * img_area)
        )

        if not is_giant_bubble:
            cv2.fillPoly(char_mask, [cnt], 255)

    inverted_mask = cv2.bitwise_not(char_mask)
    clean_img = cv2.bitwise_or(gray, inverted_mask)

    return clean_img
