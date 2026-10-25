"""The L lock needs retaining bowls between the stacking connector banks."""
import unittest

from vault.shell import build_shell
from vault.spec import ModuleSpec


class LockRecessTests(unittest.TestCase):
    def test_l_center_and_bank_catches_follow_depth_and_height(self):
        for spec in (ModuleSpec('L', 3, 1), ModuleSpec('L', 6, 2)):
            with self.subTest(spec=spec):
                shell = build_shell(spec)
                self.assertTrue(shell.is_valid)
                self.assertEqual(len(shell.solids()), 1)
                self.assertEqual(len(shell.shells()), 1)
                for x in (0, *spec.bank_centers):
                    for upper in (False, True):
                        def point(y, z):
                            return (x, y, spec.height - z if upper else z)
                        # Bowl removes the inner skin, leaving a solid floor.
                        self.assertFalse(shell.is_inside(point(spec.depth - 8, 2)))
                        self.assertTrue(shell.is_inside(point(spec.depth - 8, .5)))
                        # Skin before and after the catch remains intact.
                        self.assertTrue(shell.is_inside(point(spec.depth - 10, 2)))
                        self.assertTrue(shell.is_inside(point(spec.depth - 4, 2)))


if __name__ == '__main__':
    unittest.main()
