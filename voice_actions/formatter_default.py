from __future__ import annotations


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    result = text
    for pattern in sorted(replacements, key=len, reverse=True):
        result = result.replace(pattern, replacements[pattern])
    return result


def format_default(text: str, replacements: dict[str, str]) -> str:
    result = apply_replacements(text, replacements)
    result = result.replace("пробел", " ")
    result = result.replace("точка", ".")
    return " ".join(result.split()) if "  " in result else result
