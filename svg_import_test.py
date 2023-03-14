from math import pi
import pathlib
import tempfile
import unittest
from io import StringIO

from build123d.topology import Face, Shape, Wire
from svg_import import (
    edges_from_svg_path,
    faces_from_svg_path,
    import_svg_document,
    wires_from_svg_path,
)


class TestSvgImport(unittest.TestCase):
    def test_doc_buffer(self):
        svg = StringIO('<svg><path d="M 0,1 L 2,3"/></svg>')
        assert len(list(import_svg_document(svg))) == 1

    def test_doc_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".svg") as f:
            f.write('<svg><path d="M 0,1 L 2,3"/></svg>')
            f.flush()
            assert len(list(import_svg_document(f.name))) == 1
            assert len(list(import_svg_document(pathlib.Path(f.name)))) == 1

    def test_doc_with_id_attr(self):
        svg = StringIO(
            """<svg>
                <path id="path1" fill="none" d="M 0,10 v 3"/>
                <path id="path2" d="M 0,0 v 2 h 2 z"/>
            </svg>"""
        )
        imported = list(import_svg_document(svg, label_by="id"))
        assert len(imported) == 2

        self.assertIsInstance(imported[0], Wire)
        self.assertEqual(imported[0].label, "path1")

        self.assertIsInstance(imported[1], Face)
        self.assertEqual(imported[1].label, "path2")

    def test_doc_with_class_attr(self):
        svg = StringIO(
            """<svg>
                <path class="path1" fill="none" d="M 0,10 v 3"/>
                <path class="path2" d="M 0,0 v 2 h 2 z"/>
            </svg>"""
        )
        imported = list(import_svg_document(svg, label_by="class"))
        assert len(imported) == 2

        self.assertIsInstance(imported[0], Wire)
        self.assertEqual(imported[0].label, "path1")

        self.assertIsInstance(imported[1], Face)
        self.assertEqual(imported[1].label, "path2")

    def test_doc_with_colors(self):
        svg = StringIO(
            """<svg>
                <path id="path1" fill="blue" d="M 0,10 v 3"/>
                <path id="path2" fill="none" stroke="red" d="M 0,0 v 2 h 2 z"/>
            </svg>"""
        )
        imported = list(import_svg_document(svg, label_by="id"))
        assert len(imported) == 2

        self.assertIsInstance(imported[0], Face)
        self.assertEqual(imported[0].color.to_tuple(), (0.0, 0.0, 1.0, 1.0))

        self.assertIsInstance(imported[1], Wire)
        self.assertEqual(imported[1].color.to_tuple(), (1.0, 0.0, 0.0, 1.0))

    def test_non_path_shapes(self):
        svg = StringIO(
            """<svg>
                <rect id="rect1" x="0" y="1" width="2" height="3"/>
                <circle id="circle1" cx="4" cy="5" r="6"/>
            </svg>"""
        )
        imported = list(import_svg_document(svg))
        self.assertEqual([type(o) for o in imported], [Face, Face])

    def test_doc_file_file_error(self):
        with self.assertRaises(IOError):
            assert len(list(import_svg_document("not/an/existing/file"))) == 1

    def test_doc_syntax_error(self):
        with self.assertRaises(SyntaxError):
            svg = StringIO('<svg><path d="M 0,1 L 2,3"/>')
            list(import_svg_document(svg))

    def test_path_syntax_error(self):
        with self.assertRaises(SyntaxError):
            list(wires_from_svg_path("M 0,0 FFF 1 h 1"))

    def test_simple_path_to_wire(self):
        res = list(wires_from_svg_path("M 0,0 v 1 h 1"))
        assert len(res) == 1
        self.assertIsInstance(res[0], Wire)

    def test_arc_flags(self):
        c = pi * 45**2
        s = (45 * 2) ** 2
        cases = [
            ("M  80  80 A 45 45, 0, 0, 0, 125 125 L 125  80 Z", c / 4),
            ("M 230  80 A 45 45, 0, 1, 0, 275 125 L 275  80 Z", 3 / 4 * c + s / 4),
            ("M  80 230 A 45 45, 0, 0, 1, 125 275 L 125 230 Z", 1 / 4 * (s - c)),
            ("M 230 230 A 45 45, 0, 1, 1, 275 275 L 275 230 Z", 3 / 4 * c),
        ]
        for path, area in cases:
            res = list(faces_from_svg_path(path))
            assert len(res) == 1
            self.assertIsInstance(res[0], Face)
            self.assertAlmostEqual(res[0].area, area)

    def test_arcs_path_to_wire(self):
        """this path is continuous but introduces small discontinuities when making the edges"""
        res = list(
            wires_from_svg_path(
                "M 10 315 L 110 215"
                "A 30 50 0 0 1 162.55 162.45"
                "L 172.55 152.45"
                "A 30 50 -45 0 1 215.1 109.9"
                "L 315 10"
            )
        )
        assert len(res) == 1
        self.assertIsInstance(res[0], Wire)

    def test_empty_paths(self):
        self.assertFalse(list(edges_from_svg_path("")))
        self.assertFalse(list(wires_from_svg_path("")))
        self.assertFalse(list(faces_from_svg_path("")))

    def test_simple_path_to_face(self):
        res = list(faces_from_svg_path("M 0,0 v 1 h 1 z"))
        assert len(res) == 1
        self.assertIsInstance(res[0], Face)

    def test_simple_open_path_to_face(self):
        res = list(faces_from_svg_path("M 0,0 v 1 h 1"))
        assert len(res) == 1
        self.assertIsInstance(res[0], Face)

    def test_complex_path_to_wires(self):
        res = list(wires_from_svg_path("M 0,0 v 1 M 1,0 v 2"))
        assert len(res) == 2
        self.assertIsInstance(res[0], Wire)
        self.assertIsInstance(res[1], Wire)

    def test_complex_path_to_faces(self):
        res = list(wires_from_svg_path("M 0,0 v 1 h 1 z M 2,0 v 1 h 1"))
        assert len(res) == 2
        self.assertIsInstance(res[0], Wire)
        self.assertIsInstance(res[1], Wire)

    def test_complex_path_to_wonky_faces(self):
        # TODO degenerate?
        res = list(faces_from_svg_path("M 0,0 v 1 M 1,0 v 2"))
        assert len(res) == 2
        self.assertIsInstance(res[0], Face)
        self.assertIsInstance(res[1], Face)

    def test_concentric_path_nesting_even(self):
        """`n*2` concentric paths should yield `n` faces with one hole"""
        n = 3
        expected_hole_counts = [1] * n
        res = list(faces_from_svg_path(self.nested_squares_path(n * 2)))
        self.assertEqual(self.hole_counts(res), expected_hole_counts)

    def test_concentric_path_nesting_odd(self):
        """`n*2+1` concentric paths should yield `n` faces with one hole and 1 face with no holes"""
        n = 3
        expected_hole_counts = [0] + [1] * n
        res = list(faces_from_svg_path(self.nested_squares_path(n * 2 + 1)))
        self.assertEqual(self.hole_counts(res), expected_hole_counts)

    def test_path_nesting(self):
        """This path:
        ```
            .-----------------------------------.
            |   .----------------------------.  |
            |   | .--------------.  .-----.  |  |
            |   | | .---.        |  `-----'  |  |
            |   | | |   |  .---. |  .-----.  |  |
            |   | | `---'  `---' |  |     |  |  |
            |   | `--------------'  `-----'  |  |
            |   `----------------------------'  |
            `-----------------------------------'
        ```
        should translate to these faces (order irrelevant):
        ```
            AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
            AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
            AAAAA BBBBBBBBBBBBBBBB  CCCCCCC  AAAA
            AAAAA BBB   BBBBBBBBBB  CCCCCCC  AAAA
            AAAAA BBB   BBB     BB  DDDDDDD  AAAA
            AAAAA BBB   BBB     BB  DDDDDDD  AAAA
            AAAAA BBBBBBBBBBBBBBBB  DDDDDDD  AAAA
            AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
            AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        ```
        """
        res = list(
            faces_from_svg_path(
                "M 1,4 L 16,4 L 16,13 L 1,13 L 1,4 Z"
                "M 2,5 L 15,5 L 15,12 L 2,12 L 2,5 Z"
                "M 11,8 L 14,8 L 14,11 L 11,11 L 11,8 Z"
                "M 11,6 L 14,6 L 14,7 L 11,7 L 11,6 Z"
                "M 3,6 L 10,6 L 10,11 L 3,11 L 3,6 Z"
                "M 7,8 L 9,8 L 9,10 L 7,10 L 7,8 Z"
                "M 4,7 L 6,7 L 6,10 L 4,10 L 4,7 Z"
            )
        )

        expected_hole_counts = [0, 0, 1, 2]
        self.assertEqual(self.hole_counts(res), expected_hole_counts)

    @staticmethod
    def nested_squares_path(count: int, x: float = 0, y: float = 0):
        def parts():
            for s in range(1, count + 1):
                yield f"M{x-s},{y-s} H{x+s} V{y+s} H{x-s} Z"

        return " ".join(parts())

    @staticmethod
    def hole_counts(maybe_faces: list[Shape]):
        return sorted(
            len(face.inner_wires()) for face in maybe_faces if isinstance(face, Face)
        )
