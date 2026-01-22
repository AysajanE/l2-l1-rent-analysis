import unittest


class SmokeTest(unittest.TestCase):
    def test_smoke(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
