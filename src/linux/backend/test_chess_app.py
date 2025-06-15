import unittest
from app import parse_move  # Ensure your main code is refactored into a module

class TestChessApp(unittest.TestCase):

    def test_parse_move_simple(self):
        """Test simple move parsing."""
        self.assertEqual(parse_move("e2 e4"), "e2e4")
        self.assertEqual(parse_move("b1 c3"), "b1c3")

        self.assertEqual(parse_move("e2e 3"), "e2e3")
        self.assertEqual(parse_move("c2p 1"), "c2p1")


if __name__ == '__main__':
    unittest.main()
