from __future__ import annotations

import re

from .formatter_default import apply_replacements

TOKEN_REPLACEMENTS = {
    "точка с запятой": ";",
    "точка": ".",
    "запятая": ",",
    "равно": "=",
    "плюс": "+",
    "минус": "-",
    "тире": "-",
    "умножить": "*",
    "звёздочка": "*",
    "звездочка": "*",
    "делить": "/",
    "слэш": "/",
    "больше": ">",
    "меньше": "<",
    "скобки": "()",
    "скобка": "()",
    "квадратные скобки": "[]",
    "фигурные скобки": "{}",
    "кавычки": '""',
    "двойные кавычки": '""',
    "одинарные кавычки": "''",
    "пробел": " ",
    "ноль": "0",
    "один": "1",
    "два": "2",
    "три": "3",
    "четыре": "4",
    "пять": "5",
    "шесть": "6",
    "семь": "7",
    "восемь": "8",
    "девять": "9",
}

KEYWORDS = {
    "если": "Если",
    "тогда": "Тогда",
    "иначе": "Иначе",
    "конец если": "КонецЕсли;",
    "конецесли": "КонецЕсли;",
    "для": "Для",
    "каждого": "Каждого",
    "из": "Из",
    "цикл": "Цикл",
    "конец цикла": "КонецЦикла;",
    "конеццикла": "КонецЦикла;",
    "процедура": "Процедура",
    "конец процедура": "КонецПроцедуры",
    "конецпроцедуры": "КонецПроцедуры",
    "функция": "Функция",
    "конец функция": "КонецФункции",
    "конецфункции": "КонецФункции",
    "null": "NULL",
    "нал": "NULL",
    "ну": "NULL",
    "истина": "Истина",
    "ложь": "Ложь",
    "неопределено": "Неопределено",
}


def _replace_phrases(text: str, mapping: dict[str, str]) -> str:
    result = text
    for phrase in sorted(mapping, key=len, reverse=True):
        result = re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", mapping[phrase], result)
    return result


def _camelize_identifier(words: str) -> str:
    parts = [part for part in words.split() if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _compact_identifiers(text: str) -> str:
    operators = set("=+-*/<>,;()[]{}.")
    out: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            out.append(_camelize_identifier(" ".join(buffer)))
            buffer.clear()

    for token in text.split():
        if token in operators or all(ch in operators for ch in token):
            flush()
            out.append(token)
        elif token in KEYWORDS.values() or token in {"NULL", "Истина", "Ложь", "Неопределено"}:
            flush()
            out.append(token)
        elif re.fullmatch(r"\d+", token):
            flush()
            out.append(token)
        else:
            buffer.append(token)
    flush()
    return " ".join(out)


def _cleanup_spacing(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\.\s*", ".", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*;\s*", ";\n", text)
    text = re.sub(r"\s*=\s*", " = ", text)
    text = re.sub(r"\s*([+\-*/<>])\s*", r" \1 ", text)
    text = re.sub(r"\s+\(\)", "()", text)
    text = re.sub(r"\s+\[\]", "[]", text)
    text = re.sub(r"\s+\{\}", "{}", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\[\s+", "[", text)
    text = re.sub(r"\s+\]", "]", text)
    text = re.sub(r"\{\s+", "{", text)
    text = re.sub(r"\s+\}", "}", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def format_1c(text: str, replacements: dict[str, str]) -> str:
    result = (text or "").strip().lower()
    result = _replace_phrases(result, KEYWORDS)
    result = _replace_phrases(result, TOKEN_REPLACEMENTS)
    result = apply_replacements(result, replacements)
    result = _compact_identifiers(result)
    return _cleanup_spacing(result)
