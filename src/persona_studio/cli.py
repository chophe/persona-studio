from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from persona_studio.config import (
    INFLUENCERS_DIR,
    TEMPLATE_SLUG,
    init_influencer,
    list_influencer_slugs,
    load_influencer,
)
from persona_studio.health import run_health_checks
from persona_studio.image_analyzer import run_analysis
from persona_studio.language import lang_label
from persona_studio.prompts import list_images, list_prompts, list_videos
from persona_studio.settings import resolve_settings
from persona_studio.story import generate_story, synthesize_reports
from persona_studio.ui import (
    confirm,
    interactive_mode,
    pick_folder,
    pick_lang,
)

app = typer.Typer(
    name="persona-studio",
    help="Config-driven influencer persona pipeline: image analysis, story synthesis, RP generation",
    add_completion=False,
)
console = Console()


def _lang(lang: str | None) -> str:
    if lang and lang not in ("fa", "en"):
        console.print(f"[red]Error:[/red] Unsupported language '{lang}'. Choose from: fa, en.")
        raise typer.Exit(1)
    return lang or "fa"


def _interactive(flag: bool) -> bool:
    if not flag:
        return False
    if not interactive_mode():
        console.print("[yellow]stdin is not a TTY; continuing non-interactively.[/yellow]")
        return False
    return True


def _show_lang(lang: str) -> str:
    return f"{lang} ({lang_label(lang)})"


def _resolve(slug: str):
    try:
        return load_influencer(slug)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)


def _settings(influencer=None, model=None, base_url=None, api_key=None, max_workers=None):
    try:
        return resolve_settings(influencer, model, base_url, api_key, max_workers)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)


def _preflight(influencer, strict: bool = False) -> None:
    report = run_health_checks(influencer.slug)
    issues = [c for c in report.checks if not c.ok]
    if not issues:
        return
    console.print("[bold yellow]Preflight:[/bold yellow]")
    for check in issues:
        tag = "[yellow]warn[/yellow]" if check.warning_only else "[red]fail[/red]"
        console.print(f"  {tag} {check.name}: {check.detail}")
    if strict and report.failures:
        console.print("[red]Aborting: preflight failures (--strict).[/red]")
        raise typer.Exit(1)


def _render_health(report) -> None:
    table = Table(title=f"Health: {report.slug}")
    table.add_column("Check", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="green")
    for check in report.checks:
        if check.ok:
            status = "[green]✓ ok[/green]"
        elif check.warning_only:
            status = "[yellow]⚠ warn[/yellow]"
        else:
            status = "[red]✗ fail[/red]"
        table.add_row(check.name, status, check.detail)
    console.print(table)


@app.command()
def doctor(slug: Optional[str] = typer.Argument(None, help="Influencer slug. Checks all when omitted.")):
    """Health-check an influencer: config, persona, portrait, images, API key."""
    targets = [slug] if slug else list_influencer_slugs()
    if not targets:
        console.print("[yellow]No influencers configured. Run:[/yellow] persona-studio init <slug>")
        raise typer.Exit(1)
    any_fail = False
    for target in targets:
        report = run_health_checks(target)
        _render_health(report)
        failures = report.failures
        warnings = report.warnings
        if failures or warnings:
            any_fail = any_fail or bool(failures)
            label = f"{len(failures)} failure(s), {len(warnings)} warning(s)"
            color = "red" if failures else "yellow"
            glyph = "✗" if failures else "⚠"
            console.print(f"[{color}]{glyph} {target}: {label}[/{color}]")
        else:
            console.print(f"[green]✓ {target}: all checks passed[/green]")
    if any_fail:
        raise typer.Exit(1)


@app.command()
def personas():
    """List configured influencers."""
    slugs = list_influencer_slugs()
    if not slugs:
        console.print("[yellow]No influencers found. Run:[/yellow] persona-studio init <slug>")
        return
    table = Table(title="Influencers")
    table.add_column("Slug", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Handle")
    for slug in slugs:
        cfg = load_influencer(slug)
        table.add_row(slug, cfg.display_name, cfg.handle or "—")
    console.print(table)


@app.command()
def show(slug: str):
    """Show an influencer's config and persona summary."""
    influencer = _resolve(slug)
    body = [
        f"[bold]Name:[/bold] {influencer.display_name}"
        + (f" ({influencer.name.persian})" if influencer.name.persian else ""),
        f"[bold]Handle:[/bold] {influencer.handle or '—'}",
        f"[bold]Persona file:[/bold] {influencer.persona_path()}",
        f"[bold]Portrait:[/bold] {influencer.portrait or '—'}",
        f"[bold]Images dir:[/bold] {influencer.images_dir()}",
        f"[bold]Reports dir:[/bold] {influencer.reports_dir()}",
        f"[bold]Stories dir:[/bold] {influencer.stories_dir()}",
        f"[bold]Model defaults:[/bold] {influencer.defaults.model}",
    ]
    if influencer.special_prompts:
        body.append(f"[bold]Special prompts:[/bold] {', '.join(influencer.special_prompts)}")
    console.print(Panel("\n".join(body), title=f"{slug}", border_style="cyan"))
    try:
        persona_text = influencer.load_persona_text()
        preview = persona_text[:600]
        console.print(Panel(preview + ("\n..." if len(persona_text) > 600 else ""), title="Persona"))
    except FileNotFoundError:
        console.print("[yellow]Persona file not found yet.[/yellow]")


@app.command()
def prompts(slug: Optional[str] = typer.Argument(None)):
    """List shared and per-influencer prompts."""
    influencer = load_influencer(slug) if slug else None
    found = list_prompts(influencer)
    table = Table(title="Prompts")
    table.add_column("Name", style="cyan")
    table.add_column("File", style="green")
    for name, path in found.items():
        table.add_row(name, str(path))
    console.print(table)


@app.command()
def analyze(
    slug: str,
    prompt_name: Optional[str] = typer.Argument(
        None,
        help="Prompt name (without .md). Defaults to 'video_analysis' when --video is set.",
    ),
    images_dir: Optional[Path] = typer.Option(None, "--images", help="Override images folder"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Override output folder"),
    video: bool = typer.Option(False, "--video", "-v", help="Analyze videos (mp4, mov, ...) instead of images"),
    no_persona: bool = typer.Option(False, "--no-persona", help="Skip persona context injection"),
    rewrite: bool = typer.Option(False, "--rewrite", "-r", help="Re-analyze media even if a report already exists"),
    lang: Optional[str] = typer.Option(None, "--lang", "-l", help="Result language: fa (Persian) | en"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Prompt for inputs"),
    model: Optional[str] = typer.Option(None),
    base_url: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None),
    max_workers: Optional[int] = typer.Option(None),
    strict: bool = typer.Option(False, "--strict", help="Abort on preflight failures"),
):
    """Analyze a folder of images (or videos with --video) for an influencer using a named prompt."""
    influencer = _resolve(slug)
    settings = _settings(influencer, model, base_url, api_key, max_workers)
    if _interactive(interactive):
        lang = pick_lang(lang)
        if images_dir is None:
            images_dir = pick_folder("Images folder", influencer.images_dir())
        if output_dir is None:
            output_dir = pick_folder("Output folder", influencer.reports_dir() / (prompt_name or "video_analysis"))
    lang = _lang(lang)
    if video and not prompt_name:
        prompt_name = "video_analysis"
    if not prompt_name:
        console.print("[red]Error:[/red] A prompt name is required (or use --video).")
        raise typer.Exit(1)
    _preflight(influencer, strict=strict)
    source_dir = images_dir or influencer.images_dir()
    media = "video" if video else "image"
    files = list_videos(source_dir) if video else list_images(source_dir)
    kind = "video" if video else "image"
    if not files:
        console.print(
            f"[red]No {kind} files found in {source_dir}.[/red] "
            f"Run [cyan]persona-studio doctor {slug}[/cyan] for details."
        )
        raise typer.Exit(1)
    console.print(
        f"[dim]Influencer:[/dim] {influencer.display_name} | "
        f"[dim]Language:[/dim] {_show_lang(lang)} | "
        f"[dim]Prompt:[/dim] {prompt_name} | "
        f"[dim]Media:[/dim] {kind}"
    )
    results = run_analysis(
        influencer,
        prompt_name,
        settings,
        images_dir=images_dir,
        output_dir=output_dir,
        include_persona=not no_persona,
        lang=lang,
        rewrite=rewrite,
        media=media,
    )
    success = sum(1 for r in results.values() if r["status"] == "success")
    skipped = sum(1 for r in results.values() if r["status"] == "skipped")
    errors = sum(1 for r in results.values() if r["status"] == "error")
    console.print(
        f"\n[bold green]Done.[/bold green] Total: {len(results)} | "
        f"Success: {success} | Skipped: {skipped} | Errors: {errors}"
    )


@app.command()
def synthesize(
    slug: str,
    prompt_name: str = typer.Argument(...),
    input_dirs: list[Path] = typer.Argument(..., help="One or more dirs of markdown reports"),
    output_dir: Optional[Path] = typer.Option(None, "--out"),
    lang: Optional[str] = typer.Option(None, "--lang", "-l", help="Result language: fa (Persian) | en"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Prompt for inputs"),
    model: Optional[str] = typer.Option(None),
    base_url: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None),
    strict: bool = typer.Option(False, "--strict", help="Abort on preflight failures"),
):
    """Batch-synthesize markdown reports (e.g. per-image analyses) into narrative summaries."""
    influencer = _resolve(slug)
    settings = _settings(influencer, model, base_url, api_key)
    if _interactive(interactive):
        lang = pick_lang(lang)
        if not input_dirs:
            input_dirs = [pick_folder("Reports folder")]
        if output_dir is None:
            output_dir = pick_folder("Synthesis output", influencer.syntheses_dir() / prompt_name)
    lang = _lang(lang)
    _preflight(influencer, strict=strict)
    console.print(
        f"[dim]Influencer:[/dim] {influencer.display_name} | "
        f"[dim]Language:[/dim] {_show_lang(lang)} | "
        f"[dim]Prompt:[/dim] {prompt_name}"
    )
    try:
        master = synthesize_reports(
            influencer, prompt_name, settings, list(input_dirs), output_dir, lang=lang
        )
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"[bold green]Synthesis complete:[/bold green] {master}")


@app.command()
def story(
    slug: str,
    prompt_name: str = typer.Argument(..., help="Story prompt name (e.g. task3(c)-story)"),
    context: list[Path] = typer.Option([], "--context", help="Extra markdown context files"),
    lang: Optional[str] = typer.Option(None, "--lang", "-l", help="Result language: fa (Persian) | en"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Prompt for inputs"),
    model: Optional[str] = typer.Option(None),
    base_url: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None),
    strict: bool = typer.Option(False, "--strict", help="Abort on preflight failures"),
):
    """Generate a story/RP content from the influencer persona plus a named prompt."""
    influencer = _resolve(slug)
    settings = _settings(influencer, model, base_url, api_key)
    if _interactive(interactive):
        lang = pick_lang(lang)
        if not context and confirm("Add extra context files?", default=False):
            context = [pick_folder("Context folder")]
    lang = _lang(lang)
    _preflight(influencer, strict=strict)
    console.print(
        f"[dim]Influencer:[/dim] {influencer.display_name} | "
        f"[dim]Language:[/dim] {_show_lang(lang)} | "
        f"[dim]Prompt:[/dim] {prompt_name}"
    )
    output_file = generate_story(influencer, prompt_name, settings, list(context), lang=lang)
    console.print(f"[bold green]Story written:[/bold green] {output_file}")


@app.command()
def init(
    slug: str,
    name: str = typer.Option("", "--name", help="Display name in English"),
    handle: Optional[str] = typer.Option(None, "--handle"),
):
    """Create a new influencer from the template in influencers/_template."""
    try:
        target = init_influencer(slug, name, handle)
    except (FileExistsError, FileNotFoundError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"[green]Created[/green] {target}")
    console.print("Next: edit [cyan]config.yaml[/cyan], [cyan]persona.md[/cyan], and special prompts.")


if __name__ == "__main__":
    app()
