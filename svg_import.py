import logging
import pathlib
from collections import defaultdict
from itertools import chain
from typing import Iterable, Optional, TextIO, Union, cast

import svgelements
from svgpathtools import Arc, CubicBezier, Line, Path, QuadraticBezier

from build123d.build_enums import AngularDirection
from build123d.geometry import Axis, Plane
from build123d.topology import RAD2DEG, Edge, Face, Wire

logger = logging.getLogger(__name__)

INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"

SvgPathLike = Union[str, Path]


def import_svg_document(
    svg_file: Union[str, pathlib.Path, TextIO],
    *,
    label_by: Optional[str] = "id",
    mirror: bool = True,
):
    """Import shapes from an SVG document as faces and/or wires.

    Args:
        svg_file: svg file path or file object
        label_by: name of SVG attribute to use as wire/face label
        flip_y: whether to mirror the Y-coordinates to compensate for SVG's top left origin

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
            faces_or_wires = faces_from_svg_path(path)
        else:
            faces_or_wires = wires_from_svg_path(path)

        label = None
        if label_by:
            try:
                label = svgelements_path.values[label_by]
            except (KeyError, AttributeError):
                pass

        for face_or_wire in faces_or_wires:
            if mirror:
                face_or_wire = cast(Union[Face, Wire], face_or_wire.mirror(Plane.XZ))
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


def faces_from_svg_path(path: SvgPathLike):
    """Convert an SVG path to faces.

    Args:
        path: svg path to convert

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
        outer_wires = list(wires_from_svg_path(exterior))
        if outer_wires:
            outer_wire, *extra_outer_wires = outer_wires
            inner_wires = [
                known_continuous_edges_to_wire(edges_from_svg_path(interior))
                for interior in interiors
            ]
            if extra_outer_wires:
                logger.warning("exterior path produced multiple outer wires")
                yield Face.make_from_wires(outer_wire, extra_outer_wires + inner_wires)
            else:
                yield Face.make_from_wires(outer_wire, inner_wires)


def wires_from_svg_path(path: SvgPathLike):
    """Convert an SVG path to wires.

    Args:
        path: svg path to convert

    Raises:
        SyntaxError:

    Yields:
        wire
    """

    path = path_from_SvgPathLike(path)
    subpaths: list[Path] = path.continuous_subpaths()
    for subpath in subpaths:
        if subpath:
            yield known_continuous_edges_to_wire(edges_from_svg_path(subpath))


def edges_from_svg_path(path: SvgPathLike):
    """Convert an SVG path to edges.

    Args:
        path: svg path to convert

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
            if segment.sweep:
                angular_direction = AngularDirection.COUNTER_CLOCKWISE
            else:
                angular_direction = AngularDirection.CLOCKWISE

            plane = Plane.XY
            plane.origin = v(segment.center)
            start_angle = segment.theta
            end_angle = segment.theta + segment.delta
            ellipse = Edge.make_ellipse(
                x_radius=segment.radius.real,
                y_radius=segment.radius.imag,
                plane=plane,
                start_angle=min(start_angle, end_angle),
                end_angle=max(start_angle, end_angle),
                angular_direction=angular_direction,
            ).rotate(Axis(plane.origin, plane.z_dir.to_tuple()), segment.phi * RAD2DEG)
            yield cast(Edge, ellipse)


def known_continuous_edges_to_wire(edges: Iterable[Edge]):
    """Make a single wire from known-good edges; with no reordering nor splitting"""
    return Wire.make_wire(fill_gaps_between_edges(edges, 1e-7))
    # tolerance value has been established empirically, increasing it to `1e-6` fails some tests
    # probably linked to some OCCT value we could use instead of hardcoding?


def fill_gaps_between_edges(edges: Iterable[Edge], tolerance: float):
    """Insert line segments between edges that are more that `tolerance` apart"""
    it = filter(Edge.is_valid, edges)
    try:
        edge = next(it)
        yield edge
        end = edge.end_point()
        while True:
            edge = next(it)
            if abs(edge.start_point() - end) > tolerance:
                yield Edge.make_line(end, edge.start_point())
            yield edge
            end = edge.end_point()
    except StopIteration:
        pass


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
