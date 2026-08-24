from __future__ import annotations

from io import BytesIO

import pytest
import yaml
from PIL import Image

from persona_studio import config
from persona_studio import health


@pytest.fixture
def influencers_dir(tmp_path, monkeypatch):
    target = tmp_path / "influencers"
    target.mkdir()
    monkeypatch.setattr(config, "INFLUENCERS_DIR", target)
    return target


def make_influencer(influencers_dir, slug, data=None):
    root = influencers_dir / slug
    root.mkdir(parents=True)
    default = {
        "name": {"english": slug.title(), "persian": ""},
        "handle": "@handle",
        "persona_file": "persona.md",
        "portrait": "portrait.jpg",
        "special_prompts": ["special/notes.md"],
    }
    default.update(data or {})
    (root / "config.yaml").write_text(yaml.safe_dump(default), encoding="utf-8")
    (root / "persona.md").write_text("# Persona\n\nSome persona text.\n", encoding="utf-8")
    special = root / "special"
    special.mkdir(exist_ok=True)
    (special / "notes.md").write_text("Special instruction.\n", encoding="utf-8")
    return root


def make_portrait(path):
    buf = BytesIO()
    Image.new("RGB", (64, 48), (200, 100, 50)).save(buf, format="JPEG")
    path.write_bytes(buf.getvalue())


class TestFormatSize:
    def test_bytes(self):
        assert health._format_size(512) == "512 B"

    def test_kb(self):
        assert health._format_size(2048) == "2.0 KB"

    def test_mb(self):
        assert health._format_size(3 * 1024 * 1024) == "3.0 MB"


class TestCheckPersona:
    def test_missing_file(self, influencers_dir):
        root = make_influencer(influencers_dir, "gal", {"persona_file": "nope.md"})
        result = health.check_persona(config.load_influencer("gal"))
        assert not result.ok
        assert not result.warning_only
        assert "nope.md" in result.detail

    def test_ok(self, influencers_dir):
        make_influencer(influencers_dir, "gal")
        result = health.check_persona(config.load_influencer("gal"))
        assert result.ok
        assert "lines" in result.detail

    def test_todo_warning(self, influencers_dir):
        root = make_influencer(influencers_dir, "gal")
        (root / "persona.md").write_text("TODO: fill me\nTODO: and me\n", encoding="utf-8")
        result = health.check_persona(config.load_influencer("gal"))
        assert result.ok
        assert result.warning_only
        assert "2 TODO" in result.detail


class TestCheckPortrait:
    def test_not_configured(self, influencers_dir):
        make_influencer(influencers_dir, "gal", {"portrait": None})
        result = health.check_portrait(config.load_influencer("gal"))
        assert not result.ok
        assert result.warning_only

    def test_missing_file(self, influencers_dir):
        make_influencer(influencers_dir, "gal", {"portrait": "portrait.jpg"})
        result = health.check_portrait(config.load_influencer("gal"))
        assert not result.ok
        assert "missing" in result.detail.lower()

    def test_valid_image(self, influencers_dir):
        root = make_influencer(influencers_dir, "gal")
        make_portrait(root / "portrait.jpg")
        result = health.check_portrait(config.load_influencer("gal"))
        assert result.ok
        assert "64x48" in result.detail
        assert "JPEG" in result.detail

    def test_corrupt_image(self, influencers_dir):
        root = make_influencer(influencers_dir, "gal")
        (root / "portrait.jpg").write_bytes(b"not an image")
        result = health.check_portrait(config.load_influencer("gal"))
        assert not result.ok
        assert "unreadable" in result.detail


class TestCheckSpecialPrompts:
    def test_none_configured(self, influencers_dir):
        make_influencer(influencers_dir, "gal", {"special_prompts": []})
        result = health.check_special_prompts(config.load_influencer("gal"))
        assert not result.ok
        assert result.warning_only

    def test_missing_file(self, influencers_dir):
        make_influencer(influencers_dir, "gal", {"special_prompts": ["special/gone.md"]})
        result = health.check_special_prompts(config.load_influencer("gal"))
        assert not result.ok
        assert result.warning_only
        assert "missing" in result.detail

    def test_all_loaded(self, influencers_dir):
        make_influencer(influencers_dir, "gal", {"special_prompts": ["special/notes.md"]})
        result = health.check_special_prompts(config.load_influencer("gal"))
        assert result.ok
        assert result.detail.startswith("1/1")


class TestCheckImages:
    def test_dir_missing(self, influencers_dir):
        make_influencer(influencers_dir, "gal")
        result, count = health.check_images(config.load_influencer("gal"))
        assert count == 0
        assert not result.ok
        assert result.warning_only

    def test_no_images(self, influencers_dir):
        root = make_influencer(influencers_dir, "gal")
        (root / "images").mkdir()
        result, count = health.check_images(config.load_influencer("gal"))
        assert count == 0
        assert not result.ok
        assert result.warning_only

    def test_top_level_and_subfolder(self, influencers_dir):
        root = make_influencer(influencers_dir, "gal")
        images = root / "images"
        (images / "batch1").mkdir(parents=True)
        (images / "a.jpg").write_bytes(b"x")
        (images / "batch1" / "b.png").write_bytes(b"x")
        (images / "c.txt").write_bytes(b"x")
        result, count = health.check_images(config.load_influencer("gal"))
        assert count == 2
        assert result.ok
        assert "2 total" in result.detail
        assert "subfolder" in result.detail


class TestCheckOutputs:
    def test_empty_dirs(self, influencers_dir):
        make_influencer(influencers_dir, "gal")
        result = health.check_outputs(config.load_influencer("gal"))
        assert result.ok
        assert "empty" in result.detail

    def test_counts_markdown(self, influencers_dir):
        root = make_influencer(influencers_dir, "gal")
        reports = root / "output" / "reports"
        reports.mkdir(parents=True)
        (reports / "a.md").write_text("x", encoding="utf-8")
        result = health.check_outputs(config.load_influencer("gal"))
        assert "reports: 1 md file(s)" in result.detail


class TestRunHealthChecks:
    def test_unknown_slug_fails_load(self, influencers_dir):
        report = health.run_health_checks("ghost")
        names = {c.name for c in report.checks}
        assert "load-config" in names
        assert not report.healthy

    def test_full_report_shape(self, influencers_dir):
        root = make_influencer(influencers_dir, "gal")
        (root / "images").mkdir()
        make_portrait(root / "portrait.jpg")
        report = health.run_health_checks("gal")
        assert report.slug == "gal"
        names = {c.name for c in report.checks}
        assert {"config", "load-config", ".env", "api-key", "persona", "portrait", "images", "outputs"} <= names

    def test_healthy_when_all_good(self, influencers_dir, monkeypatch):
        root = make_influencer(influencers_dir, "gal")
        (root / "images").mkdir()
        make_portrait(root / "portrait.jpg")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234")
        report = health.run_health_checks("gal")
        assert report.healthy
        assert report.failures == []