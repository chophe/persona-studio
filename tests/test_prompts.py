from __future__ import annotations

import pytest

from persona_studio import config, prompts as prompts_mod


@pytest.fixture
def shared_prompts(tmp_path, monkeypatch):
    target = tmp_path / "prompts"
    target.mkdir()
    monkeypatch.setattr(prompts_mod, "SHARED_PROMPTS_DIR", target)
    return target


@pytest.fixture
def influencer(tmp_path, monkeypatch, shared_prompts):
    influencers = tmp_path / "influencers"
    influencers.mkdir()
    monkeypatch.setattr(config, "INFLUENCERS_DIR", influencers)
    root = influencers / "gal"
    (root / "prompts").mkdir(parents=True)
    cfg_data = "slug: gal\nname:\n  english: Gal\n"
    (root / "config.yaml").write_text(cfg_data, encoding="utf-8")
    return config.load_influencer("gal")


class TestFindPromptFile:
    def test_influencer_prompt_takes_precedence(self, influencer, shared_prompts):
        (shared_prompts / "mytask.md").write_text("shared version", encoding="utf-8")
        (influencer.prompts_dir / "mytask.md").write_text("influencer version", encoding="utf-8")
        path = prompts_mod.find_prompt_file("mytask", influencer)
        assert path == influencer.prompts_dir / "mytask.md"

    def test_falls_back_to_shared(self, shared_prompts):
        (shared_prompts / "only-shared.md").write_text("shared", encoding="utf-8")
        path = prompts_mod.find_prompt_file("only-shared", None)
        assert path.parent == shared_prompts

    def test_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            prompts_mod.find_prompt_file("does-not-exist")


class TestLoadPrompt:
    def test_loads_plain_content(self, shared_prompts):
        (shared_prompts / "plain.md").write_text("# Hello\n\nBody text.\n", encoding="utf-8")
        assert "Body text." in prompts_mod.load_prompt("plain")

    def test_inlines_markdown_references(self, shared_prompts):
        refs = shared_prompts / "refs"
        refs.mkdir()
        (refs / "style.md").write_text("STYLE_GUIDE_CONTENT", encoding="utf-8")
        (shared_prompts / "with-ref.md").write_text(
            "# Prompt\n\nSee [style.md](refs/style.md) for details.\n",
            encoding="utf-8",
        )
        content = prompts_mod.load_prompt("with-ref")
        assert "STYLE_GUIDE_CONTENT" in content
        assert "--- Reference: style.md ---" in content
        assert "[style.md](refs/style.md)" not in content


class TestListImages:
    def test_filters_by_extension(self, tmp_path):
        for name in ("a.jpg", "b.png", "c.txt", "d.webp", "e.jpeg"):
            (tmp_path / name).write_bytes(b"x")
        images = prompts_mod.list_images(tmp_path)
        names = {i.name for i in images}
        assert names == {"a.jpg", "b.png", "d.webp", "e.jpeg"}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert prompts_mod.list_images(tmp_path / "nope") == []
