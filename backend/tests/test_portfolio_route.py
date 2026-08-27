import pytest

from app.api.routes.portfolio import _position_weights


def test_position_weights_average_to_one():
    # Sin cap de por medio, el peso medio del resultado debe ser 1 -- la
    # cartera sigue "sumando lo mismo" que con peso igual, solo redistribuye
    # internamente según volatilidad.
    raw = {1: 0.10, 2: 0.10, 3: 0.10}  # misma volatilidad -> mismo peso
    weights = _position_weights(raw)
    assert weights[1] == pytest.approx(1.0)
    assert weights[2] == pytest.approx(1.0)
    assert weights[3] == pytest.approx(1.0)


def test_position_weights_less_volatile_gets_more_weight():
    # raw_weights son 1/ATR% -- un ticker más tranquilo (ATR% menor) tiene un
    # raw_weight mayor y debe terminar pesando más que uno más volátil.
    raw = {"quiet": 1 / 0.02, "volatile": 1 / 0.08}  # ATR% 2% vs 8%
    weights = _position_weights(raw)
    assert weights["quiet"] > weights["volatile"]


def test_position_weights_capped_at_bounds():
    # Un ticker extremadamente tranquilo frente a otros muy volátiles no debe
    # superar el cap de 2.0x, ni uno extremadamente volátil caer por debajo
    # de 0.5x.
    raw = {"ultra_quiet": 1 / 0.001, "normal_a": 1 / 0.05, "normal_b": 1 / 0.05}
    weights = _position_weights(raw)
    assert weights["ultra_quiet"] == 2.0

    raw2 = {"ultra_volatile": 1 / 0.50, "normal_a": 1 / 0.05, "normal_b": 1 / 0.05}
    weights2 = _position_weights(raw2)
    assert weights2["ultra_volatile"] == 0.5


def test_position_weights_missing_atr_gets_neutral_weight():
    # Sin ATR disponible para un ticker (histórico insuficiente), recibe el
    # peso medio de los que sí tienen dato -- tras normalizar, peso 1.0
    # exacto (neutro), en vez de excluir la posición del cálculo.
    raw = {1: 1 / 0.05, 2: 1 / 0.05, 3: None}
    weights = _position_weights(raw)
    assert weights[3] == 1.0


def test_position_weights_empty_input():
    assert _position_weights({}) == {}
