from __future__ import annotations

import os
from dataclasses import dataclass, field

import dotenv
from PIL import Image

from persona_studio.config import REPO_ROOT, InfluencerConfig, list_influencer_slugs, load_influencer
from persona_studio.prompts import list_images

dotenv.load_dotenv(REPO_ROOT / ".env")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    warning_only: bool = False

    @property
    def status(self) -> str:
        if self.ok:
            return "ok"
        return "warn" if self.warning_only else "fail"


@dataclass
class HealthReport:
    slug: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok and not c.warning_only]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok and c.warning_only]

    @property
    def healthy(self) -> bool:
        return not self.failures


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def check_config() -> CheckResult:
    try:
        slugs = list_influencer_slugs()
        return CheckResult("config", True, f"{len(slugs)} influencer(s) registered")
    except Exception as exc:
        return CheckResult("config", False, f"Error listing influencers: {exc}")


def check_persona(influencer: InfluencerConfig) -> CheckResult:
    path = influencer.persona_path()
    if not path.exists():
        return CheckResult("persona", False, f"Missing persona file: {path}")
    text = path.read_text(encoding="utf-8")
    todos = text.count("TODO")
    detail = f"{path.name}: {_format_size(path.stat().st_size)}, {len(text.splitlines())} lines"
    if todos:
        detail += f", {todos} TODO placeholder(s)"
    return CheckResult("persona", True, detail, warning_only=bool(todos))


def check_portrait(influencer: InfluencerConfig) -> CheckResult:
    if not influencer.portrait:
        return CheckResult("portrait", False, "No portrait configured in config.yaml", warning_only=True)
    path = influencer.resolve(influencer.portrait)
    if not path.exists():
        return CheckResult("portrait", False, f"Portrait file missing: {path}")
    size = _format_size(path.stat().st_size)
    try:
        with Image.open(path) as img:
            width, height = img.size
            fmt = img.format or "?"
    except Exception as exc:
        return CheckResult("portrait", False, f"{path.name}: unreadable image ({exc})")
    return CheckResult(
        "portrait",
        True,
        f"{path.name}: {width}x{height} {fmt}, {size}",
    )


def check_special_prompts(influencer: InfluencerConfig) -> CheckResult:
    if not influencer.special_prompts:
        return CheckResult("special-prompts", False, "No special prompts configured", warning_only=True)
    problems: list[str] = []
    loaded = 0
    for entry in influencer.special_prompts:
        path = influencer.resolve(entry)
        if path.exists():
            loaded += 1
        elif "/" not in entry and len(entry) > 40:
            loaded += 1
        else:
            problems.append(f"{entry} (missing)")
    if problems:
        return CheckResult(
            "special-prompts", False, "; ".join(problems), warning_only=True
        )
    return CheckResult("special-prompts", True, f"{loaded}/{len(influencer.special_prompts)} loaded")


def check_images(influencer: InfluencerConfig) -> tuple[CheckResult, int]:
    images_dir = influencer.images_dir()
    if not images_dir.is_dir():
        return (
            CheckResult("images", False, f"Images dir does not exist: {images_dir}", warning_only=True),
            0,
        )
    top_level = list_images(images_dir)
    recursive = sorted(
        p
        for p in images_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"
        }
    )
    total_size = sum(p.stat().st_size for p in recursive)
    subfolders = len({p.parent for p in recursive}) - 1 if recursive else 0
    if not recursive:
        return (
            CheckResult("images", False, f"No images found in {images_dir}", warning_only=True),
            0,
        )
    detail = f"{len(top_level)} top-level, {len(recursive)} total ({_format_size(total_size)})"
    if subfolders > 0:
        detail += f", {subfolders} subfolder(s)"
    return CheckResult("images", True, detail), len(recursive)


def check_outputs(influencer: InfluencerConfig) -> CheckResult:
    parts: list[str] = []
    for label, getter in (
        ("reports", influencer.reports_dir),
        ("syntheses", influencer.syntheses_dir),
        ("stories", influencer.stories_dir),
    ):
        directory = getter()
        if directory.is_dir():
            md_count = len(list(directory.rglob("*.md")))
            parts.append(f"{label}: {md_count} md file(s)")
        else:
            parts.append(f"{label}: empty")
    return CheckResult("outputs", True, " | ".join(parts), warning_only=False)


def check_api_key(base_url: str | None = None) -> CheckResult:
    key = os.getenv("OPENAI_API_KEY")
    resolved_base = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    if not key:
        return CheckResult(
            "api-key", False, "OPENAI_API_KEY not set (.env or environment)", warning_only=True
        )
    masked = key[:4] + "***" + key[-4:] if len(key) > 8 else key[:2] + "***"
    return CheckResult("api-key", True, f"{masked} -> {resolved_base}")


def check_env_file() -> CheckResult:
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        return CheckResult(".env", True, str(env_path))
    return CheckResult(".env", False, f"Not found at {env_path} (copy .env.template)", warning_only=True)


def run_health_checks(slug: str) -> HealthReport:
    report = HealthReport(slug=slug)
    report.checks.append(check_config())
    try:
        influencer = load_influencer(slug)
    except (FileNotFoundError, ValueError) as exc:
        report.checks.append(CheckResult("load-config", False, str(exc)))
        return report

    report.checks.append(CheckResult("load-config", True, f"{influencer.display_name}" + (f" ({influencer.handle})" if influencer.handle else "")))
    report.checks.append(check_env_file())
    report.checks.append(check_api_key())
    result = check_persona(influencer)
    report.checks.append(result)
    report.checks.append(check_portrait(influencer))
    report.checks.append(check_special_prompts(influencer))
    images_result, _ = check_images(influencer)
    report.checks.append(images_result)
    report.checks.append(check_outputs(influencer))
    return report
