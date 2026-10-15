import unittest

import numpy as np
import pandas as pd

from anomaly import normalise_categories, prepare_categories


class CategoryCleaningTests(unittest.TestCase):
    def test_formatting(self):
        result = normalise_categories(
            pd.Series(["  WHITE   MICA ", "white mica", "White Mica"])
        )
        self.assertEqual(result.tolist(), ["white mica"] * 3)

    def test_missing_and_meaningful_labels(self):
        result = normalise_categories(
            pd.Series([None, np.nan, "", " NULL ", "INVALID", "Wood"])
        )
        self.assertTrue(result.iloc[:4].isna().all())
        self.assertEqual(result.iloc[4:].tolist(), ["invalid", "wood"])

    def test_distinct_species_remain_distinct(self):
        result = normalise_categories(
            pd.Series(["Chlorite-Fe", "Chlorite-Mg"])
        )
        self.assertEqual(result.nunique(), 2)

    def test_exact_duplicate_removed(self):
        data = pd.DataFrame({
            "Min1 A": ["Quartz", " Albite ", None],
            "Min1 B": ["quartz", "albite", None],
        })
        kept, dropped = prepare_categories(
            data, list(data.columns), min_valid=2
        )
        self.assertEqual(kept, ["Min1 A"])
        self.assertEqual(dropped, {"Min1 B": "Min1 A"})

    def test_different_values_missingness_and_roles_retained(self):
        data = pd.DataFrame({
            "Min1 A": ["quartz", "albite", None],
            "Min1 B": ["quartz", "gypsum", None],
            "Min1 C": ["quartz", None, "albite"],
            "Min2 A": ["quartz", "albite", None],
        })
        kept, dropped = prepare_categories(
            data, list(data.columns), min_valid=2
        )
        self.assertEqual(kept, list(data.columns))
        self.assertEqual(dropped, {})

    def test_default_requires_1000_valid_readings(self):
        data = pd.DataFrame({
            "Min1 A": ["quartz"] * 999,
            "Min1 B": ["quartz"] * 999,
        })
        kept, dropped = prepare_categories(data, list(data.columns))
        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, {})

        data.loc[999] = ["quartz", "quartz"]
        kept, dropped = prepare_categories(data, list(data.columns))
        self.assertEqual(kept, ["Min1 A"])
        self.assertEqual(dropped, {"Min1 B": "Min1 A"})


if __name__ == "__main__":
    unittest.main()