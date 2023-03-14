from collections import defaultdict
from itertools import chain

from build123d import Compound, Face, Iterable, Shape, ShapeList, Solid, Vector, Wire

from svg_import import INKSCAPE_LABEL, import_svg_document


def _show_object(o: Shape):
    try:
        show_object(o.wrapped)  # type: ignore
    except NameError:
        print(o, o.color)


def collect_by_label(shapes: Iterable[Shape]):
    faces: dict[str, ShapeList[Face]] = defaultdict(ShapeList)
    wires: dict[str, ShapeList[Wire]] = defaultdict(ShapeList)
    for shape in shapes:
        if isinstance(shape, Face):
            faces[shape.label].append(shape)
        elif isinstance(shape, Wire):
            wires[shape.label].append(shape)
    return faces, wires


def extrude(faces: Iterable[Face], d: float):
    v = Vector(0, 0, d)
    return Compound.make_compound(Solid.extrude_linear(face, v) for face in faces)


faces, _wires = collect_by_label(
    import_svg_document("inkscape-drawing.svg", label_by=INKSCAPE_LABEL)
)

face = extrude(faces.pop("face"), 3).translate((0, 0, 6))
head = extrude(faces.pop("head"), 8)
body = extrude(chain.from_iterable(faces.values()), 5)
robot = head.cut(face).fuse(body)

_show_object(robot)
