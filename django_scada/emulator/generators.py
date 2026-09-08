"""Stateless-генераторы значений для SimulatorDevice.

Все формулы зависят только от текущего времени (time.time() % period),
промежуточное состояние не хранится — рестарт процесса безопасен.
"""

import math
import random
import time


def compute_value(mode, min_value, max_value, period=60, now=None, signal_type=""):
    now = time.time() if now is None else now
    if mode == "constant":
        return float(min_value)
    if mode == "random":
        return float(random.uniform(min_value, max_value))
    if mode == "sine":
        period = period or 60
        mid = (min_value + max_value) / 2.0
        amp = (max_value - min_value) / 2.0
        phase = 2.0 * math.pi * ((now % period) / period)
        return float(mid + amp * math.sin(phase))
    if mode == "ramp":
        period = period or 60
        frac = (now % period) / period
        return float(min_value + (max_value - min_value) * frac)
    if mode == "cycle":
        # Циклический перебор [min, max] (для digital_input обычно 0/1).
        # Переключение каждые period/2 сек: при period=4 тик раз в 2 сек
        # даёт 0/1/0/1... — stateless, без хранения индекса.
        period = period or 4
        values = _cycle_values(signal_type, min_value, max_value)
        slot = period / len(values)
        idx = int(now // slot) % len(values)
        return float(values[idx])
    raise ValueError(f"Unknown mode: {mode}")


def _cycle_values(signal_type, min_value, max_value):
    if signal_type == "digital_input":
        lo, hi = int(round(min_value)), int(round(max_value))
        if lo == hi:
            return [float(lo)]
        # Классика 0/1 независимо от порядка min/max
        return [float(lo), float(hi)] if {lo, hi} != {0, 1} else [0.0, 1.0]
    if min_value == max_value:
        return [float(min_value)]
    return [float(min_value), float(max_value)]


def compute_for_simulator(sim, now=None):
    """Удобный враппер: принимает объект SimulatorDevice."""
    return compute_value(
        mode=sim.mode,
        min_value=sim.min_value,
        max_value=sim.max_value,
        period=sim.period,
        now=now,
        signal_type=sim.signal_type,
    )
