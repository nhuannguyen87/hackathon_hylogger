"""Synthetic trays for core_strip.detect_core_rows - no NVCL photos needed.

    python test_core_strip.py      (or pytest)
"""

import numpy as np

import core_strip as cs


def tray(rows, core=70, empty_last=False, missing_rail=None, width=2000):
    """A tray photo: black title bar, `rows` channels of textured core between
    bright rails (thin dark shadow either side), black axis strip below."""
    x = np.arange(width)
    lines = [np.zeros((40, width))]  # title bar
    for i in range(rows):
        if i != missing_rail:
            lines += [np.full((12, width), 225.0), np.full((3, width), 20.0)]  # rail, shadow
        grain = core + 18 * np.sin(x / 37.0) + 9 * np.sin(x / 5.3)  # varies along the core, not across it
        grain[(x % 311) < 4] = 25  # fractures
        fill = np.full((140, width), 235.0) if empty_last and i == rows - 1 else np.tile(grain, (140, 1))
        lines += [fill, np.full((3, width), 20.0)]
    lines += [np.full((12, width), 225.0), np.zeros((60, width))]  # last rail, axis strip
    return np.vstack(lines).astype(np.float32)


def rows_in(image):
    x0, y0, x1, y1 = cs._trim_chrome(image)
    return cs.detect_core_rows(image[y0:y1, x0:x1])


def test_dark_and_pale_core():
    assert len(rows_in(tray(5, core=60))) == 5  # darker than the rails: the old brightness split failed here
    assert len(rows_in(tray(4, core=190))) == 4


def test_missed_rail_is_split():
    rows = rows_in(tray(5, missing_rail=2))
    assert len(rows) == 5
    heights = [b - a for a, b in rows]
    assert max(heights) < 1.3 * min(heights)


def test_trailing_empty_channel_dropped():
    assert len(rows_in(tray(5, empty_last=True))) == 4


if __name__ == "__main__":
    test_dark_and_pale_core()
    test_missed_rail_is_split()
    test_trailing_empty_channel_dropped()
    print("core_strip row detection: ok")
