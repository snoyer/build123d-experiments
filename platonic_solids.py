import re
from itertools import chain, product
from typing import Iterable

from build123d import Align, Face, Shell, Solid, Text, Vector, VectorLike, Wire
from pyhull.convex_hull import ConvexHull


def convexhull_of_points(points: Iterable[VectorLike]):
    vectors = [Vector(point) for point in points]
    faces = ConvexHull([v.to_tuple() for v in vectors]).vertices
    return Solid.make_solid(
        Shell.make_shell(
            Face.make_from_wires(Wire.make_polygon(vectors[i] for i in face))
            for face in faces
        )
    )


def expand_coords(coords: tuple[str, str, str]) -> Iterable[tuple[float, float, float]]:
    """`('1', '±2', '3')` -> `[(1, -2, 3), (1, 2, 3)]`"""
    CONSTANTS = {
        "φ": (1 + 5**0.5) / 2,
        "1/φ": 2 / (1 + 5**0.5),
    }

    def parse_v(s: str) -> float:
        return float(CONSTANTS.get(s, s))

    def expand_plusminus(s: str):
        s = s.strip()
        if s[0] == "±":
            v = parse_v(s[1:])
            yield +v
            yield -v
        else:
            yield parse_v(s)

    return product(*map(expand_plusminus, coords))


def parse_coords(coords: str) -> Iterable[tuple[float, float, float]]:
    """`"(1, ±2, 3) (±4, 5, 6)"` -> `[(1, -2, 3), (1, 2, 3), (-4, 5, 6), (4, 5 ,6)]`"""
    return chain.from_iterable(
        map(
            expand_coords,
            (xyz.split(",") for xyz in re.findall(r"\(([^)]+)\)", coords)),
        )
    )


platonic_solids = {
    "tetrahedron": "(1, 1, 1) (1, -1, -1) (-1, 1, -1) (-1, -1, 1)",
    # "tetrahedron2": "(-1, -1, -1) (-1, 1, 1) (1, -1, 1) (1, 1, -1)",
    "octahedron": "(±1, 0, 0) (0, ±1, 0) (0, 0, ±1)",
    "cube": "(±1, ±1, ±1)",
    "icosahedron": "(0, ±1, ±φ) (±1, ±φ, 0) (±φ, 0, ±1)",
    # "isocahedron2": "(0, ±φ, ±1) (±φ, ±1, 0) (±1, 0, ±φ)",
    "dodecahedron": "(±1, ±1, ±1) (0, ±1/φ, ±φ) (±1/φ, ±φ, 0) (±φ, 0, ±1/φ)",
    # "dodecahedron2": "(±1, ±1, ±1) (0, ±φ, ±1/φ) (±φ, ±1/φ, 0) (±1/φ, 0, ±φ)",
}

for i, (name, coords_str) in enumerate(platonic_solids.items()):
    solid = convexhull_of_points(parse_coords(coords_str)).clean()
    solid = solid.scale(1 / solid.vertices()[0].center().length)
    label = Text(
        coords_str.replace(") ", ")\n"),
        0.3,
        align=(Align.CENTER, Align.MAX),
    ).translate((0, -1, 0))

    t = i * 2.5, 0, 0
    show_object(solid.translate(t).wrapped)
    show_object(label.translate(t).wrapped)
