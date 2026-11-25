import unittest
from xml.etree.ElementTree import fromstring

from coverage_badges import badge, combined_coverage


class CoverageBadgeTests(unittest.TestCase):
    def test_weights_line_counts_instead_of_averaging_percentages(self):
        result = combined_coverage(
            {'covered_lines': 2115, 'num_statements': 2173},
            {'covered': 932, 'total': 1336},
        )
        self.assertAlmostEqual(result, 86.83385579937304)

    def test_empty_or_invalid_counts_are_rejected(self):
        for covered, total in [(0, 0), (2, 1), (-1, 1)]:
            with self.subTest(covered=covered, total=total), self.assertRaises(ValueError):
                combined_coverage({'covered_lines': covered, 'num_statements': total}, {'covered': 0, 'total': 0})

    def test_badge_uses_measured_value_and_threshold_color(self):
        passing = badge('develop coverage', 85)
        failing = badge('main coverage', 84.99)
        self.assertIn('85.00%', passing)
        self.assertIn('#4c1', passing)
        self.assertIn('#e05d44', failing)
        fromstring(passing)
        fromstring(failing)
