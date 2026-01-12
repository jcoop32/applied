import unittest
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api.profile import parse_date_string

class TestProfileDateParsing(unittest.TestCase):
    def test_parse_month_year(self):
        res = parse_date_string("Jan 2023")
        self.assertEqual(res, {"month": "January", "year": "2023"})

        res = parse_date_string("January 2024")
        self.assertEqual(res, {"month": "January", "year": "2024"})

    def test_parse_year_only(self):
        res = parse_date_string("2022")
        self.assertEqual(res, {"month": "", "year": "2022"})

    def test_parse_present(self):
        res = parse_date_string("Present")
        self.assertTrue(res.get("is_current"))
    
    def test_parse_empty(self):
        res = parse_date_string("")
        self.assertEqual(res, {"month": "", "year": ""})

if __name__ == '__main__':
    unittest.main()
