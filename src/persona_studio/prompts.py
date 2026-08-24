from __future__ import annotations

import re
from pathlib import Path

from persona_studio.config import SHARED_PROMPTS_DIR, InfluencerConfig

_REFERENCE_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv", ".wmv", ".mpg", ".mpeg"}


def find_prompt_file(prompt_name: str, influencer: InfluencerConfig | None = None) -> Path:
    candidates: list[Path] = []
    if influencer is not None:
        candidates.append(influencer.prompts_dir / f"{prompt_name}.md")
    candidates.append(SHARED_PROMPTS_DIR / f"{prompt_name}.md")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"Prompt '{prompt_name}' not found (searched: {searched})")


def load_prompt(prompt_name: str, influencer: InfluencerConfig | None = None) -> str:
    """Load a prompt by name and inline any markdown file references.

    References use standard markdown link syntax: [name](relative/path.md).
    They are resolved relative to the prompt file's own directory.
    Image references are left untouched so they can be attached as vision inputs.
    """
    prompt_file = find_prompt_file(prompt_name, influencer)
    content = prompt_file.read_text(encoding="utf-8")
    for ref_name, ref_path in _REFERENCE_PATTERN.findall(content):
        ref_file = (prompt_file.parent / ref_path).resolve()
        if ref_file.suffix.lower() in _IMAGE_EXTENSIONS:
            continue
        if ref_file.exists():
            ref_content = ref_file.read_text(encoding="utf-8")
            content = content.replace(
                f"[{ref_name}]({ref_path})",
                f"\n--- Reference: {ref_name} ---\n{ref_content}\n--- End Reference ---\n",
            )
    return content


def list_prompts(influencer: InfluencerConfig | None = None) -> dict[str, Path]:
    found: dict[str, Path] = {}
    search_dirs: list[Path] = []
    if influencer is not None:
        search_dirs.append(influencer.prompts_dir)
    search_dirs.append(SHARED_PROMPTS_DIR)
    for base in search_dirs:
        if not base.exists():
            continue
        for md in sorted(base.glob("*.md")):
            found.setdefault(md.stem, md)
    return found


def list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        f for f in folder.rglob("*") if f.suffix.lower() in _IMAGE_EXTENSIONS and f.is_file()
    )


def list_videos(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        f for f in folder.rglob("*") if f.suffix.lower() in _VIDEO_EXTENSIONS and f.is_file()
    )
