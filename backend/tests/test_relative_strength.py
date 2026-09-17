from app.relative_strength import passes_relative_strength


def test_relative_strength_requires_two_lookbacks():
    benchmark = [100 + i for i in range(53)]
    ticker = [100 + i * 1.1 for i in range(53)]
    assert passes_relative_strength(ticker, benchmark) is True


def test_relative_strength_rejects_underperformer():
    benchmark = [100 + i for i in range(53)]
    ticker = [100 + i * 0.8 for i in range(53)]
    assert passes_relative_strength(ticker, benchmark) is False


def test_relative_strength_fails_without_aligned_history():
    assert passes_relative_strength([1, 2], [1]) is False
