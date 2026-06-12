from voice_actions.formatter_1c import format_1c


def test_basic_condition():
    assert format_1c("если сумма равно ноль тогда", {}) == "Если Сумма = 0 Тогда"


def test_dot_and_method_call():
    assert format_1c("таблица точка добавить скобки", {}) == "Таблица.Добавить()"
