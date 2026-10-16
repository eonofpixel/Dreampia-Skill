import unittest
from slots import reserve
class SlotsTests(unittest.TestCase):
    def test_reserve(self): self.assertEqual(reserve({},'09:00','alice'),{'09:00':'alice'})
    def test_duplicate_same_person(self): self.assertEqual(reserve({'09:00':'alice'},'09:00','alice'),{'09:00':'alice'})
    def test_conflict(self):
        with self.assertRaises(ValueError): reserve({'09:00':'alice'},'09:00','bob')
    def test_required(self):
        with self.assertRaises(ValueError): reserve({},'', 'alice')
