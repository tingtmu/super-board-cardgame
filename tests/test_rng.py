from cardgame.rng import make_rng


def test_same_seed_gives_identical_sequence():
    first = make_rng(42)
    second = make_rng(42)
    assert [first.random() for _ in range(20)] == [second.random() for _ in range(20)]


def test_different_seeds_give_different_sequences():
    a = make_rng(1)
    b = make_rng(2)
    assert [a.randint(0, 1000) for _ in range(10)] != [b.randint(0, 1000) for _ in range(10)]
