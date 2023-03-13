import logging
import pathlib
from collections import defaultdict
from itertools import chain
from typing import Iterable, Optional, TextIO, cast

import svgelements
from svgpathtools import Arc, CubicBezier, Line, Path, QuadraticBezier

from build123d.build_enums import AngularDirection
from build123d.geometry import Axis, Plane
from build123d.topology import RAD2DEG, Edge, Face, Wire

logger = logging.getLogger(__name__)

DEFAULT_TOL = 1e-6

SvgPathLike = str | Path


def import_svg_document(
    svg_file: str | pathlib.Path | TextIO,
    *,
    label_by: Optional[str] = "id",
    mirror: bool = True,
    tolerance: float = DEFAULT_TOL,
):
    """Import shapes from an SVG document as faces and/or wires.

    Args:
        svg_file: svg file path or file object
        label_by: name of SVG attribute to use as wire/face label
        flip_y: whether to mirror the Y-coordinates to compensate for SVG's top left origin
        tolerance: tolerance for path operations

    Raises:
        SyntaxError:
        IOError:
        ValueError:

    Yields:
        face or wire depending on whether the shapes are filled
    """

    def _path_to_svgpathtools(svgelements_path: svgelements.Path):
        """converting segments might be faster than re-parsing maybe?
        but the representations are different (segments vs commands)
        so exchanging via string is probably a safer bet."""
        return Path(str(svgelements_path))

    def _path_to_faces_or_wires(svgelements_path: svgelements.Path):
        path = _path_to_svgpathtools(svgelements_path)
        is_filled = svgelements_path.fill.value is not None
        if is_filled:
            faces_or_wires = faces_from_svg_path(path, tolerance=tolerance)
        else:
            faces_or_wires = wires_from_svg_path(path, tolerance=tolerance)

        label = None
        if label_by:
            try:
                label = svgelements_path.values[label_by]
            except (KeyError, AttributeError):
                pass

        for face_or_wire in faces_or_wires:
            if mirror:
                face_or_wire = face_or_wire.mirror(Plane.XZ)
            if label:
                face_or_wire.label = label
            yield face_or_wire

    try:
        parsed_svg = svgelements.SVG.parse(svg_file)
        for element in parsed_svg.elements():
            try:
                if element.values["visibility"] == "hidden":
                    continue
            except (KeyError, AttributeError):
                pass

            if isinstance(element, svgelements.Path):
                yield from _path_to_faces_or_wires(element)

            elif isinstance(element, svgelements.Shape):
                # TODO handle shape types instead of converting to path
                path = svgelements.Path(element)
                path.reify()
                yield from _path_to_faces_or_wires(path)

    except SyntaxError:
        raise
    except IOError:
        raise


def faces_from_svg_path(path: SvgPathLike, *, tolerance: float = DEFAULT_TOL):
    """Convert an SVG path to faces.

    Args:
        path: svg path to convert
        tolerance: tolerance for path operations

    Raises:
        SyntaxError:
        ValueError:

    Yields:
        face
    """
    path = path_from_SvgPathLike(path)

    subpaths: list[Path] = path.continuous_subpaths()
    for subpath in subpaths:
        try:
            subpath.closed = True
        except ValueError:  # not closeable
            subpath.append(Line(subpath.end, subpath.start))
            try:
                subpath.closed = True
            except ValueError:  # still not closeable
                raise ValueError("could ensure path is closed")

    for exterior, interiors in unnest_paths(*subpaths):
        wires = Wire.combine(svg_path_to_edges(exterior), tol=tolerance)
        if wires:
            outer_wire, *extra_outer_wires = wires
            inner_wires = Wire.combine(
                chain.from_iterable(
                    svg_path_to_edges(interior) for interior in interiors
                ),
                tol=tolerance,
            )
            if extra_outer_wires:
                logger.warning("exterior path produced multiple outer wires")
                yield Face.make_from_wires(outer_wire, extra_outer_wires + inner_wires)
            else:
                yield Face.make_from_wires(outer_wire, inner_wires)


def wires_from_svg_path(path: SvgPathLike, *, tolerance: float = DEFAULT_TOL):
    """Convert an SVG path to wires.

    Args:
        path: svg path to convert
        tolerance: tolerance for path operations

    Raises:
        SyntaxError:

    Yields:
        edge
    """

    path = path_from_SvgPathLike(path)
    for subpath in path.continuous_subpaths():
        yield from Wire.combine(svg_path_to_edges(subpath), tol=tolerance)
        # TODO figure out how to build wire directly instead
        # `subpath` is already continuous and ordered at that point so `combine` is overkill


def svg_path_to_edges(path: SvgPathLike):
    """Convert an SVG path to edges.

    Args:
        path: svg path to convert
        tolerance: tolerance for path operations (`1e-6' by default)

    Raises:
        SyntaxError:

    Yields:
        edge
    """

    path = path_from_SvgPathLike(path)

    def v(c: complex):
        return c.real, c.imag

    for segment in path:
        if isinstance(segment, Line):
            yield Edge.make_line(v(segment.start), v(segment.end))
        elif isinstance(segment, QuadraticBezier):
            yield Edge.make_bezier(v(segment.start), v(segment.control), v(segment.end))
        elif isinstance(segment, CubicBezier):
            yield Edge.make_bezier(
                v(segment.start),
                v(segment.control1),
                v(segment.control2),
                v(segment.end),
            )
        elif isinstance(segment, Arc):
            if segment.delta < 0:
                angular_direction = AngularDirection.CLOCKWISE
            else:
                angular_direction = AngularDirection.COUNTER_CLOCKWISE

            plane = Plane.XY
            plane.origin = v(segment.center)
            ellipse = Edge.make_ellipse(
                x_radius=segment.radius.real,
                y_radius=segment.radius.imag,
                plane=plane,
                start_angle=segment.theta,
                end_angle=segment.theta + segment.delta,
                angular_direction=angular_direction,
            ).rotate(Axis(plane.origin, plane.z_dir.to_tuple()), segment.phi * RAD2DEG)
            yield cast(Edge, ellipse)


def unnest_paths(
    *paths: Path,
) -> Iterable[tuple[Path, list[Path]]]:
    """sort non-intersecting paths into pairs of singly-nested exterior and interiors"""
    continuous_paths: list[Path] = list(
        chain.from_iterable(path.continuous_subpaths() for path in paths)
    )

    included_in: dict[int, set[int]] = defaultdict(set)
    n = len(continuous_paths)
    for i in range(n):
        for j in range(n):
            if i != j and continuous_paths[i].is_contained_by(continuous_paths[j]):
                included_in[i].add(j)

    PathListPair = tuple[list[Path], list[Path]]
    exterior_and_interiors: dict[int, PathListPair] = defaultdict(lambda: ([], []))
    for i in range(n):
        ancestors = included_in[i]
        depth = len(ancestors)
        if depth % 2:
            parent_i = max(ancestors, key=lambda i: len(included_in[i]))
            exterior_and_interiors[parent_i][1].append(continuous_paths[i])
        else:
            exterior_and_interiors[i][0].append(continuous_paths[i])

    for exteriors, interiors in exterior_and_interiors.values():
        if len(exteriors) == 1:
            yield exteriors[0], interiors
        else:
            logger.warn("invalid nesting (%d exteriors)", len(exteriors))
            # shouldn't ever get there
            # but yield everything as simple exteriors just in case
            for path in chain(interiors, exteriors):
                yield path, []


def path_from_SvgPathLike(path: SvgPathLike):
    if isinstance(path, Path):
        return path
    else:
        try:
            return Path(path)
        except Exception:
            raise SyntaxError(f"could not make svg path from: {path!r}")
