import logging

from build123d import Axis, Solid

from dihedral_filter import DiherdralFilter

logging.basicConfig(level=logging.DEBUG)


o = Solid.make_box(2, 2, 2).fuse(Solid.make_box(2, 2, 2).translate((1, 1, 0))).clean()
o = o.fillet(0.5, o.edges().filter_by(Axis.Z).filter_by(DiherdralFilter.Inside()))
o = o.chamfer(
    0.1, None, o.edges().filter_by(Axis.Z).filter_by(DiherdralFilter.Outside())
)
show_object(o.wrapped)
