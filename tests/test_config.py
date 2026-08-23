from __future__ import annotations

import shutil

import pytest
import yaml

from persona_studio import config


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
        "name": {"english": f"{slug.title()} Person", "persian": ""},
        "handle": "@handle",
        "persona_file": "persona.md",
        "special_prompts": ["special/notes.md"],
    }
    default.update(data or {})
    (root / "config.yaml").write_text(yaml.safe_dump(default), encoding="utf-8")
    (root / "persona.md").write_text("# Persona\n\nTest persona text.\n", encoding="utf-8")
    special = root / "special"
    special.mkdir(exist_ok=True)
    (special / "notes.md").write_text("Special instruction block.\n", encoding="utf-8")
    return root


class TestListSlugs:
    def test_returns_sorted_slugs(self, influencers_dir):
        make_influencer(influencers_dir, "beta")
        make_influencer(influencers_dir, "alpha")
        assert config.list_influencer_slugs() == ["alpha", "beta"]

    def test_excludes_template(self, influencers_dir):
        make_influencer(influencers_dir, config.TEMPLATE_SLUG)
        make_influencer(influencers_dir, "real")
        assert config.list_influencer_slugs() == ["real"]

    def test_missing_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INFLUENCERS_DIR", tmp_path / "nope")
        assert config.list_influencer_slugs() == []


class TestLoadInfluencer:
    def test_loads_and_validates(self, influencers_dir):
        make_influencer(influencers_dir, "testa")
        cfg = config.load_influencer("testa")
        assert cfg.slug == "testa"
        assert cfg.display_name == "Testa Person"
        assert cfg.handle == "@handle"

    def test_unknown_slug_raises(self, influencers_dir):
        with pytest.raises(FileNotFoundError):
            config.load_influencer("ghost")

    def test_template_slug_rejected(self, influencers_dir):
        make_influencer(influencers_dir, "_template")
        with pytest.raises(FileNotFoundError):
            config.load_influencer("_template")

    def test_invalid_yaml_schema_raises(self, influencers_dir):
        root = influencers_dir / "bad"
        root.mkdir()
        (root / "config.yaml").write_text(yaml.safe_dump({"name": 42}), encoding="utf-8")
        with pytest.raises(ValueError):
            config.load_influencer("bad")


class TestInfluencerPaths:
    def test_resolve_relative(self, influencers_dir):
        make_influencer(influencers_dir, "paths")
        cfg = config.load_influencer("paths")
        assert cfg.images_dir() == cfg.root / "images"

    def test_persona_text(self, influencers_dir):
        make_influencer(influencers_dir, "ptext")
        cfg = config.load_influencer("ptext")
        assert "Test persona text." in cfg.load_persona_text()

    def test_special_prompts_loaded(self, influencers_dir):
        make_influencer(influencers_dir, "sp")
        cfg = config.load_influencer("sp")
        blocks = cfg.load_special_prompts()
        assert len(blocks) == 1
        assert "Special instruction block." in blocks[0]

    def test_context_block(self, influencers_dir):
        make_influencer(influencers_dir, "ctx")
        cfg = config.load_influencer("ctx")
        block = cfg.build_context_block()
        assert "# Persona:" in block
        assert "@handle" in block
        assert "Test persona text." in block
        assert "Special instruction block." in block


class TestInitInfluencer:
    def test_creates_from_template(self, tmp_path, monkeypatch, influencers_dir):
        template = influencers_dir / "_template"
        shutil.copytree(
            config.REPO_ROOT / "influencers" / "_template",
            template,
            ignore=shutil.ignore_patterns("images", "output"),
        )
        created = config.init_influencer("newgal", name_english="New Gal", handle="@newgal")
        assert (created / "config.yaml").exists()
        cfg = config.load_influencer("newgal")
        assert cfg.display_name == "New Gal"
        assert cfg.handle == "@newgal"
