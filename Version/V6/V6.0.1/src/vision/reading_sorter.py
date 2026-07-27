from typing import List, Tuple
import numpy as np


def sort_manga_reading_order(
    boxes: List[Tuple[int, int, int, int]]
) -> List[Tuple[int, int, int, int]]:
    if not boxes:
        return []

    arr = np.array(boxes, dtype=np.float64)
    x, y, w, h = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    cy = y + h / 2.0

    order = np.argsort(cy)
    sorted_arr = arr[order]

    n = len(sorted_arr)
    visited = np.zeros(n, dtype=bool)
    groups = []

    for i in range(n):
        if visited[i]:
            continue

        visited[i] = True
        group = [i]

        unvisited = np.where(~visited)[0]
        if len(unvisited) > 0:
            ya, ha = sorted_arr[i, 1], sorted_arr[i, 3]
            yb, hb = sorted_arr[unvisited, 1], sorted_arr[unvisited, 3]

            inter_max = np.minimum(ya + ha, yb + hb)
            inter_min = np.maximum(ya, yb)
            intersection = np.maximum(0.0, inter_max - inter_min)
            min_h = np.minimum(ha, hb)

            overlaps = np.where(min_h > 0, intersection / min_h, 0.0)
            matched = unvisited[overlaps > 0.5]

            visited[matched] = True
            group.extend(matched.tolist())

        groups.append(group)

    result = []
    for group_indices in groups:
        g_arr = sorted_arr[group_indices]
        g_cx = g_arr[:, 0] + g_arr[:, 2] / 2.0
        g_cy = g_arr[:, 1]

        sort_key = np.lexsort((g_cy, -g_cx))
        for idx in sort_key:
            b = g_arr[idx]
            result.append((int(b[0]), int(b[1]), int(b[2]), int(b[3])))

    return result
