"""Unit tests for ``map_click``'s pixel-resolution helper.

``map_click`` clicks a NAMED map polygon by computing a point guaranteed to lie
INSIDE it, projecting that to screen pixels, and dispatching a real click. The
projection + click need a live Mapbox map (a browser), but the load-bearing,
failure-prone bit — "find a point actually inside this (possibly concave) ward,
not a centroid that falls in a hole or the notch of an L-shape" — is pure
geometry. That's isolated as ``polygon_interior_point`` so it can be pinned here
without a browser. A wrong point clicks the WRONG ward (or empty canvas), so this
is the part most worth a test.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.recorder import (  # noqa: E402
    _point_in_ring,
    _ring_centroid,
    polygon_interior_point,
)


def _square():
    # closed unit square ring (GeoJSON style: first == last)
    return [[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0], [0.0, 0.0]]]


def _l_shape():
    # An L / concave polygon whose bounding-box centre (≈ (3,3)) falls in the
    # MISSING corner — a naive centroid would land outside the polygon.
    return [
        [
            [0.0, 0.0],
            [6.0, 0.0],
            [6.0, 2.0],
            [2.0, 2.0],
            [2.0, 6.0],
            [0.0, 6.0],
            [0.0, 0.0],
        ]
    ]


def _square_with_hole():
    outer = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]
    # A hole dead-centre, so the centroid (5,5) lands IN the hole → must be rejected.
    hole = [[3.0, 3.0], [7.0, 3.0], [7.0, 7.0], [3.0, 7.0], [3.0, 3.0]]
    return [outer, hole]


def test_centroid_used_for_convex_polygon():
    pt = polygon_interior_point(_square())
    assert pt == (2.0, 2.0)  # exact centroid of the unit-square ring
    assert _point_in_ring(pt, _square()[0])


def test_concave_polygon_point_is_inside_not_centroid():
    rings = _l_shape()
    cx, cy = _ring_centroid(rings[0])
    # The shoelace centroid of this L falls in the missing corner → NOT inside.
    assert not _point_in_ring((cx, cy), rings[0])
    pt = polygon_interior_point(rings)
    # The helper must instead return a representative interior point.
    assert _point_in_ring(pt, rings[0]), f"{pt} should be inside the L-shape"


def test_polygon_with_hole_avoids_the_hole():
    rings = _square_with_hole()
    outer, hole = rings[0], rings[1]
    # Centroid lands in the hole → must be rejected for an interior sample.
    assert _point_in_ring((5.0, 5.0), hole)
    pt = polygon_interior_point(rings)
    assert _point_in_ring(pt, outer), f"{pt} should be inside the outer ring"
    assert not _point_in_ring(pt, hole), f"{pt} must NOT be inside the hole"


def test_empty_rings_raise():
    import pytest

    with pytest.raises(ValueError):
        polygon_interior_point([])
    with pytest.raises(ValueError):
        polygon_interior_point([[]])


def test_point_in_ring_basic():
    sq = _square()[0]
    assert _point_in_ring((2.0, 2.0), sq)
    assert not _point_in_ring((5.0, 5.0), sq)
    assert not _point_in_ring((-1.0, 2.0), sq)
