from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
INFLUENCERS_DIR = REPO_ROOT / "influencers"
SHARED_PROMPTS_DIR = REPO_ROOT / "prompts"
TEMPLATE_SLUG = "_template"


class NameConfig(BaseModel):
    english: str = ""
    persian: str = ""


class DefaultsConfig(BaseModel):
    model: str = "gpt-4o-mini"
    vision_model: str | None = None
    synthesis_model: str | None = None
    temperature: float = 0.1
    max_tokens: int = 4096
    max_workers: int = 3
    context_window: int = 128000


class PathsConfig(BaseModel):
    images: str = "images"
    reports: str = "output/reports"
    syntheses: str = "output/syntheses"
    stories: str = "stories"


class InfluencerConfig(BaseModel):
    slug: str
    name: NameConfig = Field(default_factory=NameConfig)
    handle: str | None = None
    persona_file: str = "persona.md"
    portrait: str | None = None
    special_prompts: list[str] = Field(default_factory=list)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @property
    def root(self) -> Path:
        return INFLUENCERS_DIR / self.slug

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"

    @property
    def display_name(self) -> str:
        return self.name.english or self.name.persian or self.slug

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else self.root / path

    def images_dir(self) -> Path:
        return self.resolve(self.paths.images)

    def reports_dir(self) -> Path:
        return self.resolve(self.paths.reports)

    def syntheses_dir(self) -> Path:
        return self.resolve(self.paths.syntheses)

    def stories_dir(self) -> Path:
        return self.resolve(self.paths.stories)

    def persona_path(self) -> Path:
        return self.resolve(self.persona_file)

    def load_persona_text(self) -> str:
        path = self.persona_path()
        if not path.exists():
            raise FileNotFoundError(f"Persona file not found: {path}")
        return path.read_text(encoding="utf-8")

    def load_special_prompts(self) -> list[str]:
        blocks: list[str] = []
        for entry in self.special_prompts:
            path = self.resolve(entry)
            if path.exists():
                blocks.append(path.read_text(encoding="utf-8"))
            else:
                blocks.append(entry.strip())
        return blocks

    def build_context_block(self) -> str:
        sections = [f"# Persona: {self.display_name}", ""]
        if self.handle:
            sections.append(f"Instagram handle: {self.handle}")
        if self.portrait and self.resolve(self.portrait).exists():
            sections.append(f"Reference portrait: {self.portrait} (attached as image)")
        sections.append("")
        sections.append("## Persona description")
        sections.append(self.load_persona_text())
        for i, block in enumerate(self.load_special_prompts(), start=1):
            sections.append("")
            sections.append(f"## Special instructions {i}")
            sections.append(block)
        return "\n".join(sections)


def list_influencer_slugs(include_template: bool = False) -> list[str]:
    if not INFLUENCERS_DIR.exists():
        return []
    slugs = sorted(
        d.name
        for d in INFLUENCERS_DIR.iterdir()
        if d.is_dir() and (d / "config.yaml").exists()
    )
    if include_template:
        return slugs
    return [s for s in slugs if s != TEMPLATE_SLUG]


def load_influencer(slug: str) -> InfluencerConfig:
    config_file = INFLUENCERS_DIR / slug / "config.yaml"
    if slug == TEMPLATE_SLUG or not config_file.exists():
        available = ", ".join(list_influencer_slugs()) or "none"
        raise FileNotFoundError(
            f"No config.yaml for influencer '{slug}'. Available: {available}. "
            f"Copy influencers/{TEMPLATE_SLUG}/ to get started."
        )
    data: dict[str, Any] = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    try:
        return InfluencerConfig.model_validate({**data, "slug": slug})
    except ValidationError as exc:
        raise ValueError(f"Invalid config for '{slug}': {exc}") from exc


def init_influencer(slug: str, name_english: str = "", handle: str | None = None) -> Path:
    target = INFLUENCERS_DIR / slug
    if target.exists():
        raise FileExistsError(f"Influencer directory already exists: {target}")
    template_root = INFLUENCERS_DIR / TEMPLATE_SLUG
    if not template_root.exists():
        raise FileNotFoundError(f"Template missing: {template_root}")
    import shutil

    shutil.copytree(template_root, target)
    config_file = target / "config.yaml"
    data: dict[str, Any] = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    data["name"] = {"english": name_english or slug}
    if handle:
        data["handle"] = handle
    config_file.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target
