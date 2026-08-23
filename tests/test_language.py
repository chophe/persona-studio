from __future__ import annotations

import pytest

from persona_studio.language import (
    inject_language,
    lang_label,
    lang_suffix,
    language_directive,
    normalize_lang,
)


class TestNormalizeLang:
    def test_defaults_to_persian(self):
        assert normalize_lang("") == "fa"

    def test_lowercases_and_truncates(self):
        assert normalize_lang("en") == "en"
        assert normalize_lang("EN") == "en"
        assert normalize_lang("ENGLISH") == "en"

    def test_partial_unknown_truncation_raises(self):
        with pytest.raises(ValueError):
            normalize_lang("Persian")

    def test_unsupported_raises(self):
        with pytest.raises(ValueError):
            normalize_lang("de")


class TestSuffix:
    def test_persian_suffix(self):
        assert lang_suffix("fa") == "-fa"

    def test_english_suffix(self):
        assert lang_suffix("en") == "-en"


class TestLabels:
    def test_persian_label(self):
        assert "Persian" in lang_label("fa")

    def test_english_label(self):
        assert lang_label("en") == "English"


class TestDirective:
    def test_persian_directive_mentions_persian(self):
        assert "Persian" in language_directive("fa")

    def test_english_directive(self):
        assert "English" in language_directive("en")


class TestInjectLanguage:
    def test_appends_directive(self):
        result = inject_language("Analyze this.", "en")
        assert result.startswith("Analyze this.")
        assert "Language" in result
        assert "English" in result

    def test_injects_fa_directive(self):
        result = inject_language("Analyze this.", "fa")
        assert "فارسی" in result

    def test_bad_lang_raises(self):
        with pytest.raises(ValueError):
            inject_language("x", "zz")
