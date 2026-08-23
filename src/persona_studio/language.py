from __future__ import annotations

from typing import Literal

Lang = Literal["fa", "en"]

LANGS: tuple[str, ...] = ("fa", "en")

SUFFIX: dict[str, str] = {"fa": "-fa", "en": "-en"}

LABELS: dict[str, str] = {
    "fa": "Persian (فارسی)",
    "en": "English",
}

DIRECTIVES: dict[str, str] = {
    "fa": (
        "Respond entirely in Persian (فارسی). All prose, headings, and labels "
        "must be written in Persian. Keep technical terms or proper names as-is."
    ),
    "en": (
        "Respond entirely in English. All prose, headings, and labels must be "
        "written in English."
    ),
}


def normalize_lang(lang: str) -> str:
    value = (lang or "fa").lower().strip()[0:2]
    if value not in LANGS:
        raise ValueError(f"Unsupported language '{lang}'. Choose from: {', '.join(LANGS)}.")
    return value


def lang_suffix(lang: str) -> str:
    return SUFFIX[normalize_lang(lang)]


def lang_label(lang: str) -> str:
    return LABELS[normalize_lang(lang)]


def language_directive(lang: str) -> str:
    return DIRECTIVES[normalize_lang(lang)]


def inject_language(prompt_text: str, lang: str) -> str:
    directive = language_directive(lang)
    return f"{prompt_text.rstrip()}\n\n---\n\n## Language\n{directive}"
