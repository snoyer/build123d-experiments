from typing import Iterable, Optional, Tuple

import build123d as bd
import cadquery as cq
from cadquery.occ_impl.assembly import AssemblyObjects, AssemblyProtocol
from OCP.TopoDS import TopoDS_Compound, TopoDS_Solid


class B123dAssemblyProtocol(AssemblyProtocol):
    def __init__(
        self, o: bd.Shape, parent: Optional["B123dAssemblyProtocol"] = None
    ) -> None:
        self.o = o
        self._parent = parent

    @property
    def loc(self) -> cq.Location:
        return cq.Location(self.o.location.wrapped)

    @loc.setter
    def loc(self, value: cq.Location) -> None:
        self.o.locate(bd.Location(value.wrapped))

    @property
    def name(self) -> str:
        return self.o.label

    @property
    def color(self) -> Optional[cq.Color]:
        print(self.o.color)
        if self.o.color:
            return cq.Color(*self.o.color.to_tuple())

    @property
    def obj(self) -> AssemblyObjects:
        if isinstance(self.o.wrapped, TopoDS_Solid):
            return cq.Shape(self.o.wrapped)

    @property
    def children(self) -> Iterable["AssemblyProtocol"]:
        if isinstance(self.o.wrapped, TopoDS_Compound):
            ti = bd.TopoDS_Iterator(self.o.wrapped)
            while ti.More():
                yield B123dAssemblyProtocol(bd.Shape(ti.Value()), parent=self)
                ti.Next()
        # TODO

    @property
    def parent(self) -> Optional["AssemblyProtocol"]:
        return self._parent

    @property
    def shapes(self) -> Iterable[cq.Shape]:
        cq_obj = self.obj
        if isinstance(cq_obj, cq.Shape):
            return [cq_obj]
        elif isinstance(cq_obj, cq.Workplane):
            return [e for e in cq_obj.vals() if isinstance(e, cq.Shape)]
        else:
            raise ValueError()

    def traverse(self) -> Iterable[Tuple[str, "AssemblyProtocol"]]:
        for ch in self.children:
            yield from ch.traverse()
        yield self.name, self
