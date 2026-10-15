"""
API edge cases, in the spirit of the FastAPI backend's tests
(github.com/nhuannguyen87/hylogger, backend/tests/test_api.py): a bad
parameter is a 422, an unknown hole a 404, never a 500 or a hung request.

    cd backend && python manage.py test holes

Runs against a throwaway test database with a two-hole fixture - your real
data is never touched.
"""

from rest_framework.test import APITestCase

from . import assays
from .geology import rock_family
from .geo import trace_points
from .management.commands.load_interim import choose_position, own_rows, same_hole_name
from .minerals import commodity_codes
from .models import Assay, Hole, Measurement


class ApiEdgeCases(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hole = Hole.objects.create(
            hole_id="H1", hole_name="H1", latitude=-31.0, longitude=121.0,
            borehole_length_m=10, catalog={"commodity": ["AU"]},
        )
        Hole.objects.create(hole_id="H2 [chips]", hole_name="H2", latitude=-31.01, longitude=121.01)
        for depth, group in [(0, "CHLORITE"), (1, "CHLORITE"), (2, "KAOLIN")]:
            Measurement.objects.create(
                hole=cls.hole, depth_from_m=depth, depth_to_m=depth + 1, mineral_1=group,
                confidence=0.9, mix={"swir": {group: 80, "WHITE-MICA": 20}},
                is_anomaly=depth == 2, anomaly_score=0.9 if depth == 2 else 0.1,
            )

    def assertStatus(self, url, status):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status, f"{url}: {response.content[:200]}")
        return response

    def test_bad_numbers_are_422_not_500(self):
        for url in [
            "/api/holes/?limit=abc", "/api/holes/?limit=-1", "/api/holes/?limit=1.5",
            "/api/holes/H1/trace/?step_m=abc", "/api/holes/H1/trace/?step_m=nan",
            "/api/holes/H1/nearby/?km=abc", "/api/holes/H1/nearby/?km=-5",
            "/api/holes/H1/spectral-sample/?depth_m=abc",
            "/api/mineral-logs/?min_confidence=2",
        ]:
            with self.subTest(url=url):
                self.assertStatus(url, 422)

    def test_zero_step_is_refused_not_an_endless_loop(self):
        self.assertStatus("/api/holes/H1/trace/?step_m=0", 422)
        with self.assertRaises(ValueError):
            trace_points(-90, 0, 100, step_m=0)

    def test_unknown_hole_is_404(self):
        for url in ["/api/holes/NOPE/", "/api/holes/NOPE/anomalies/",
                    "/api/holes/NOPE/minerals/", "/api/holes/NOPE/spectral-sample/"]:
            with self.subTest(url=url):
                self.assertStatus(url, 404)

    def test_missing_required_parameters_are_422(self):
        self.assertStatus("/api/distance/?a=H1", 422)
        self.assertStatus("/api/minerals/richness/", 422)
        self.assertStatus("/api/minerals/richness/?group=CHLORITE&species=Chlorite-Fe", 422)

    def test_hole_id_with_spaces_and_brackets(self):
        self.assertStatus("/api/holes/H2%20%5Bchips%5D/", 200)

    def test_trace_points_pick_the_interval_covering_their_depth(self):
        points = self.assertStatus("/api/holes/H1/trace/?step_m=0.5", 200).json()["points"]
        by_depth = {p["depth_m"]: p["mineral"] for p in points}
        self.assertEqual(by_depth[0.0], "CHLORITE")
        self.assertEqual(by_depth[1.5], "CHLORITE")
        self.assertEqual(by_depth[2.0], "KAOLIN")  # an interval's top belongs to it
        self.assertEqual(by_depth[3.0], "")        # below the last logged metre

    def test_filters_and_richness(self):
        self.assertEqual([h["hole_id"] for h in self.assertStatus("/api/holes/?commodity=AU", 200).json()], ["H1"])
        self.assertEqual([h["hole_id"] for h in self.assertStatus("/api/holes/?group=KAOLIN", 200).json()], ["H1"])
        # CHLORITE is 80% of two of H1's three metres -> 53.3% on average
        self.assertEqual(self.assertStatus("/api/minerals/richness/?group=CHLORITE", 200).json(), {"H1": 53.3})

    def test_commodity_codes(self):
        self.assertEqual(commodity_codes("Au, Cu"), ["AU", "CU"])
        self.assertEqual(commodity_codes("ZN (VMS); NI-CO"), ["ZN", "NI", "CO"])
        self.assertEqual(commodity_codes("G5 PRODUCER  EXT"), [])
        self.assertEqual(commodity_codes("GOLD; NICKEL"), ["AU", "NI"])  # DASC's spelling
        self.assertEqual(commodity_codes("NIOBIUM; RARE EARTH ELEMENTS; IRON"), ["NB", "REE", "FE"])


class AssayRules(APITestCase):
    """holes/assays.py: below detection, suspect units, best 5 m."""

    @classmethod
    def setUpTestData(cls):
        hole = Hole.objects.create(hole_id="G1", latitude=-31.0, longitude=121.0, catalog={"commodity": ["AU"]})
        Hole.objects.create(hole_id="G2", latitude=-31.1, longitude=121.1, catalog={"commodity": ["AU"]})
        Measurement.objects.create(hole=hole, depth_from_m=0, depth_to_m=1, mineral_1="CHLORITE", confidence=0.9)
        for top, au in [(0, 0.005), (1, 0.02), (2, 1.0), (3, 2.0), (4, 0.03), (5, 0.04), (6, 0.01), (7, 0.0)]:
            values, below = ({"Au": au}, []) if au else ({}, ["Au"])
            Assay.objects.create(hole=hole, depth_from_m=top, depth_to_m=top + 1, values=values,
                                 below_detection=below, collar_id="1")
        Assay.objects.create(hole=hole, depth_from_m=8, depth_to_m=9, suspect={"Au": 421300.0}, collar_id="1")

    def test_classify_codes(self):
        self.assertEqual(assays.classify("Au", -0.01), ("below_detection", None))
        self.assertEqual(assays.classify("Au", -5000), ("below_detection", None))
        self.assertEqual(assays.classify("Au", 421300.0), ("suspect", 421300.0))
        self.assertEqual(assays.classify("Fe", 620000.0), ("value", 620000.0))  # real high-grade iron ore
        self.assertEqual(assays.classify("Au", float("nan")), (None, None))

    def test_best_window(self):
        rows = [(0, 1, 0.005), (1, 2, 0.02), (2, 3, 1.0), (3, 4, 2.0), (4, 5, 0.03), (5, 6, 0.04)]
        average, top, bottom = assays.best_window(rows)
        self.assertEqual((top, bottom), (1, 6))  # 1-6 m beats 0-5 m
        self.assertAlmostEqual(average, (0.02 + 1 + 2 + 0.03 + 0.04) / 5)
        self.assertEqual(assays.best_window([(0, 2, 0.5), (2, 3, 1.5)])[0], (1 + 1.5) / 3)  # shorter than 5 m
        self.assertEqual(assays.best_window([(0, 1, None)]), None)  # a gap is not a zero
        self.assertEqual(assays.best_window([(0, 6, 0.0)])[0], 0.0)  # all below detection is a measured zero

    def test_suspect_is_left_out_of_grades(self):
        best = self.client.get("/api/holes/G1/assays/").json()["best"]["Au"]
        self.assertLess(best["ppm"], 1000)  # the 421,300 ppm unit error never reaches an average

    def test_commodity_richness_and_holes_without_assays(self):
        grades = self.client.get("/api/minerals/richness/?commodity=AU").json()
        self.assertIn("G1", grades)
        self.assertNotIn("G2", grades)  # no assays: no number, the map shows it grey
        self.assertEqual(self.client.get("/api/minerals/richness/?commodity=DIAMOND").json(), {})

    def test_export_csv(self):
        response = self.client.get("/api/holes/G1/export.csv")
        self.assertEqual(response.status_code, 200)
        lines = response.content.decode().splitlines()
        self.assertTrue(lines[0].startswith('"# G1.'))  # attribution first
        self.assertIn("Au_ppm", lines[1])
        self.assertTrue(lines[2].endswith(",0.005"))
        self.assertEqual(self.client.get("/api/holes/NOPE/export.csv").status_code, 404)

    def test_qgis_layers(self):
        holes = self.client.get("/api/qgis/holes.geojson?commodity=AU").json()["features"]
        self.assertEqual({f["properties"]["hole_id"] for f in holes}, {"G1", "G2"})
        g1 = next(f["properties"] for f in holes if f["properties"]["hole_id"] == "G1")
        self.assertAlmostEqual(g1["au_best5m_ppm"], (0.02 + 1 + 2 + 0.03 + 0.04) / 5, places=4)
        top, bottom = self.client.get("/api/qgis/intervals.geojson?holes=G1").json()["features"][0]["geometry"]["coordinates"]
        self.assertGreater(top[2], bottom[2])  # a vertical hole goes down as depth grows
        au = [f["properties"] for f in self.client.get("/api/qgis/assays.geojson?holes=G1").json()["features"]]
        self.assertTrue(any(p["below_detection"] and p["ppm"] is None for p in au))
        self.assertTrue(any(p["suspect_ppm"] == 421300.0 and p["ppm"] is None for p in au))
        self.assertEqual(self.client.get("/api/qgis/assays.geojson?element=Zz").status_code, 422)


class InterimPackage(APITestCase):
    """load_interim: which index rows a hole may use, and where it goes on the map."""

    def test_same_hole_name(self):
        self.assertEqual(same_hole_name("00KE16 [chips]"), "00KE16")
        self.assertEqual(same_hole_name("DD01 [dup. name]"), "DD01 [dup. name]")  # a namesake elsewhere
        self.assertEqual(same_hole_name("DD02 [wedge 1]"), "DD02 [wedge 1]")      # another path
        self.assertEqual(same_hole_name("DD03"), "DD03")

    def test_choose_position_keeps_the_two_that_agree(self):
        here, near, far = (-30.0, 120.0), (-30.001, 120.001), (-30.0, 126.0)
        self.assertEqual(choose_position(here, near, here), (*near, "DASC GDA2020", None))
        lat, lon, source, note = choose_position(here, far, near)  # RKD005: DASC's typo
        self.assertEqual(((lat, lon), source), (here, "NVCL catalog"))
        self.assertIn("company collar", note)
        lat, lon, source, note = choose_position(far, here, near)  # NVCL was the odd one out
        self.assertEqual(((lat, lon), source), (here, "DASC GDA2020"))
        self.assertTrue(note.startswith("Moved"))
        self.assertIn("no company collar", choose_position(far, here, None)[3])
        self.assertIn("company collar is", choose_position(here, near, far)[3])  # odd one out, still said

    def test_namesakes_lend_nothing(self):
        bh01 = {"dasc": (-30.0, 120.0), "collars": []}
        behemoth = {"dasc": (-20.0, 128.0), "collars": ["4628519"]}  # BH01_Behemoth
        self.assertEqual(own_rows([bh01, behemoth], (-30.0, 120.0)), [bh01])
        chips = {"dasc": (-30.0001, 120.0), "collars": []}
        self.assertEqual(own_rows([bh01, chips], (-25.0, 125.0)), [bh01, chips])  # same hole, any NVCL position


class LoggedRock(APITestCase):
    """holes/geology.py: a rock name finds its family; a bare code is never guessed at."""

    def test_rock_family(self):
        self.assertEqual(rock_family("basalt", ""), "mafic")
        self.assertEqual(rock_family("felsic-granulite", ""), "metamorphic")  # a granulite, whatever its make-up
        self.assertEqual(rock_family("", "Ultramafic komatiite"), "ultramafic")  # not caught by "mafic"
        self.assertEqual(rock_family("", "Claystone"), "sedimentary")
        self.assertEqual(rock_family("dolerite", "Fine-grained granite"), "mafic")  # GSWA's name comes first
        self.assertEqual(rock_family("", "Unusual stuff"), "other")
        self.assertEqual(rock_family("", ""), "code")

    def test_geology_endpoint(self):
        from .models import Geology, Hole
        hole = Hole.objects.create(hole_id="R1", latitude=-31.0, longitude=121.0)
        Geology.objects.create(hole=hole, depth_from_m=0, depth_to_m=2, code="BAS", rock="basalt", collar_id="1")
        Geology.objects.create(hole=hole, depth_from_m=2, depth_to_m=5, code="XQ7", collar_id="1")
        rows = self.client.get("/api/holes/R1/geology/").json()["intervals"]
        self.assertEqual([r["family"] for r in rows], ["mafic", "code"])
        self.assertEqual(self.client.get("/api/holes/NOPE/geology/").status_code, 404)
