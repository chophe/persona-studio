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
from persona_studio.image_analyzer import run_analysis
from persona_studio.prompts import list_prompts
from persona_studio.settings import resolve_settings
from persona_studio.story import generate_story, synthesize_reports

app = typer.Typer(
    name="persona-studio",
    help="Config-driven influencer persona pipeline: image analysis, story synthesis, RP generation",
    add_completion=False,
)
console = Console()


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
    prompt_name: str = typer.Argument(..., help="Prompt name (without .md)"),
    images_dir: Optional[Path] = typer.Option(None, "--images", help="Override images folder"),
    output_dir: Optional[Path] = typer.Option(None, "--out", help="Override output folder"),
    no_persona: bool = typer.Option(False, "--no-persona", help="Skip persona context injection"),
    model: Optional[str] = typer.Option(None),
    base_url: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None),
    max_workers: Optional[int] = typer.Option(None),
):
    """Analyze a folder of images for an influencer using a named prompt."""
    influencer = _resolve(slug)
    settings = _settings(influencer, model, base_url, api_key, max_workers)
    results = run_analysis(
        influencer,
        prompt_name,
        settings,
        images_dir=images_dir,
        output_dir=output_dir,
        include_persona=not no_persona,
    )
    success = sum(1 for r in results.values() if r["status"] == "success")
    errors = len(results) - success
    console.print(
        f"\n[bold green]Done.[/bold green] Total: {len(results)} | "
        f"Success: {success} | Errors: {errors}"
    )


@app.command()
def synthesize(
    slug: str,
    prompt_name: str = typer.Argument(...),
    input_dirs: list[Path] = typer.Argument(..., help="One or more dirs of markdown reports"),
    output_dir: Optional[Path] = typer.Option(None, "--out"),
    model: Optional[str] = typer.Option(None),
    base_url: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None),
):
    """Batch-synthesize markdown reports (e.g. per-image analyses) into narrative summaries."""
    influencer = _resolve(slug)
    settings = _settings(influencer, model, base_url, api_key)
    try:
        master = synthesize_reports(
            influencer, prompt_name, settings, list(input_dirs), output_dir
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
    model: Optional[str] = typer.Option(None),
    base_url: Optional[str] = typer.Option(None),
    api_key: Optional[str] = typer.Option(None),
):
    """Generate a story/RP content from the influencer persona plus a named prompt."""
    influencer = _resolve(slug)
    settings = _settings(influencer, model, base_url, api_key)
    output_file = generate_story(influencer, prompt_name, settings, list(context))
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
