"""Seeded random source so that every battle is reproducible."""

import random


def make_rng(seed: int) -> random.Random:
    """Return a private RNG; the same seed always yields the same sequence."""
    return random.Random(seed)
