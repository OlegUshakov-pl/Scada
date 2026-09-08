"""Юнит-тесты stateless-генераторов (без БД/Redis)."""

from django.test import SimpleTestCase

from emulator.generators import compute_value


class GeneratorTests(SimpleTestCase):
    def test_constant(self):
        self.assertEqual(compute_value("constant", 22, 22, now=1000), 22.0)

    def test_random_in_range(self):
        for _ in range(50):
            v = compute_value("random", 15, 30, now=1000)
            self.assertGreaterEqual(v, 15)
            self.assertLessEqual(v, 30)

    def test_sine_bounds_and_periodicity(self):
        vals = [compute_value("sine", 18, 26, period=300, now=t) for t in range(0, 300)]
        self.assertAlmostEqual(min(vals), 18, delta=0.1)
        self.assertAlmostEqual(max(vals), 26, delta=0.1)
        self.assertAlmostEqual(
            compute_value("sine", 18, 26, period=300, now=10),
            compute_value("sine", 18, 26, period=300, now=310),
        )

    def test_ramp_resets(self):
        self.assertAlmostEqual(compute_value("ramp", 0, 10, period=60, now=0), 0.0)
        self.assertAlmostEqual(compute_value("ramp", 0, 10, period=60, now=30), 5.0, delta=0.01)
        self.assertAlmostEqual(compute_value("ramp", 0, 10, period=60, now=60), 0.0)

    def test_cycle_toggles(self):
        # period=4 -> слот 2 сек: 0/1/0/1...
        self.assertEqual(compute_value("cycle", 0, 1, period=4, now=0, signal_type="digital_input"), 0.0)
        self.assertEqual(compute_value("cycle", 0, 1, period=4, now=2, signal_type="digital_input"), 1.0)
        self.assertEqual(compute_value("cycle", 0, 1, period=4, now=4, signal_type="digital_input"), 0.0)

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            compute_value("nope", 0, 1, now=0)
