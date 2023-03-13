from build123d import Shape
from svg_import import import_svg_document

def _show_object(o: Shape):
    label = o.label or f'0x{id(o.wrapped):0x}'
    try:
        show_object(o.wrapped, f'{type(o).__name__} {label}') #type: ignore
    except NameError:
        print(o, label)

for face_or_wire in import_svg_document('build123d_logo.svg'):
    _show_object(face_or_wire)
