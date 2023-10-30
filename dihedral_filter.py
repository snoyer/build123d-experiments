import logging
from math import pi, radians
from typing import Callable, Union, cast

from build123d import Compound, Edge, Face, Shape, ShapePredicate, TopAbs_Orientation

logger = logging.getLogger(__name__)


def find_ancestor(shape: Shape):
    result = None
    for ancestor in topo_ancestors(shape):
        result = ancestor
    return result


def topo_ancestors(shape: Shape):
    parent = shape.topo_parent
    while parent is not None:
        yield parent
        parent = parent.topo_parent


class DiherdralFilter(ShapePredicate):
    """Edge selector based on the angle between adjacent faces"""

    # we use a class and not a function so we can cache the edge->face maps

    def __init__(
        self,
        angle_predicate: Callable[[float], bool],
        *,
        in_degrees: bool = True,
        zero_epsilon: float = 1e-10,
    ):
        self.angle_predicate = angle_predicate
        self.in_degrees = in_degrees
        self.zero_epsilon = zero_epsilon
        self.edge_face_maps: dict[Union[Compound, Shape], dict[Shape, list[Shape]]] = {}

    @classmethod
    def Inside(cls):
        return cls(lambda a: a < 0)

    @classmethod
    def Outside(cls):
        return cls(lambda a: a > 0)

    @classmethod
    def Sharp(cls, threshold: float = 45, *, in_degrees: bool = True):
        return cls(lambda a: 0 < a <= threshold, in_degrees=in_degrees)

    def _edge_face_map_for_parent(self, parent: Union[Compound, Shape]):
        try:
            return self.edge_face_maps[parent]
        except KeyError:
            logger.debug("computing edge->face map for %s", parent)
            edge_face_map = parent._entities_from("Edge", "Face")
            self.edge_face_maps[parent] = edge_face_map
            return edge_face_map

    def _faces_for_edge(self, edge: Edge):
        if parent := find_ancestor(edge):
            edge_to_faces_map = self._edge_face_map_for_parent(parent)
            fs = edge_to_faces_map.get(edge)
            if fs and len(fs) == 2:
                return cast(Face, fs[0]), cast(Face, fs[1])
        raise KeyError(edge)

    def __call__(self, edge: Edge):
        try:
            f1, f2 = self._faces_for_edge(edge)

            p = edge.center()
            v1 = f1.normal_at(p)
            v2 = f2.normal_at(p)

            ref = edge.tangent_at(0)
            angle = float(v2.wrapped.AngleWithRef(v1.wrapped, ref.wrapped))
            if (
                edge.wrapped
                and edge.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
            ):
                angle = -angle

            if angle > 0:
                angle = +pi - angle
            elif angle < 0:
                angle = -pi - angle

            if not (self.zero_epsilon <= abs(angle) <= pi - self.zero_epsilon):
                angle = 0

            return self.angle_predicate(radians(angle) if self.in_degrees else angle)
        except KeyError:
            return False
