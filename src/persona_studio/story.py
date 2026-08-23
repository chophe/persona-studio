from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage
from rich.console import Console

from persona_studio.config import InfluencerConfig
from persona_studio.language import inject_language, lang_suffix, normalize_lang
from persona_studio.prompts import load_prompt
from persona_studio.settings import ApiSettings, make_llm

console = Console()

_CHARS_PER_TOKEN = 4


def batch_documents(texts: list[tuple[str, str]], context_window: int) -> list[list[str]]:
    """Batch (name, text) documents so each batch fits ~80% of the token budget."""
    budget = int(context_window * 0.8) * _CHARS_PER_TOKEN
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for _, text in texts:
        text_size = len(text)
        if current and size + text_size > budget:
            batches.append(current)
            current = []
            size = 0
        if text_size > budget:
            if current:
                batches.append(current)
                current = []
                size = 0
            batches.append([text])
            continue
        current.append(text)
        size += text_size
    if current:
        batches.append(current)
    return batches


def collect_markdown(directories: list[Path]) -> list[tuple[str, str]]:
    docs: list[tuple[str, str]] = []
    for directory in directories:
        if not directory.is_dir():
            console.print(f"[yellow]Skipping missing input dir: {directory}[/yellow]")
            continue
        for md in sorted(directory.glob("*.md")):
            docs.append((md.name, md.read_text(encoding="utf-8")))
    return docs


def synthesize_reports(
    influencer: InfluencerConfig,
    prompt_name: str,
    settings: ApiSettings,
    input_dirs: list[Path],
    output_dir: Path | None = None,
    lang: str = "fa",
) -> Path:
    lang = normalize_lang(lang)
    suffix = lang_suffix(lang)
    out_dir = output_dir or influencer.syntheses_dir() / prompt_name
    out_dir.mkdir(parents=True, exist_ok=True)

    docs = collect_markdown(input_dirs)
    if not docs:
        raise ValueError(f"No markdown files found in: {input_dirs}")
    console.print(f"[green]Collected {len(docs)} documents[/green]")

    prompt_text = inject_language(load_prompt(prompt_name, influencer), lang)
    llm = make_llm(
        ApiSettings(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=settings.synthesis_model,
            synthesis_model=settings.synthesis_model,
            max_workers=1,
        ),
        temperature=0.3,
        max_tokens=influencer.defaults.max_tokens * 2,
    )

    batches = batch_documents(docs, influencer.defaults.context_window)
    console.print(f"Processing {len(batches)} batch(es) with model {settings.synthesis_model}")

    outputs: list[str] = []
    for i, batch in enumerate(batches, start=1):
        joined = "\n\n---\n\n".join(batch)
        message = HumanMessage(content=f"{prompt_text}\n\n---\n\n{joined}")
        response = llm.invoke([message])
        output_file = out_dir / f"synthesis_batch_{i}{suffix}.md"
        output_file.write_text(
            f"# Synthesis Batch {i}\n\n**Model:** {settings.synthesis_model}\n"
            f"**Prompt:** {prompt_name}\n**Language:** {lang}\n\n## Result\n\n{response.content}",
            encoding="utf-8",
        )
        outputs.append(str(response.content))
        console.print(f"[green]✓[/green] Wrote {output_file}")

    master = out_dir / f"master_synthesis{suffix}.md"
    if len(outputs) > 1:
        master.write_text(
            "\n\n---\n\n".join(outputs), encoding="utf-8"
        )
        console.print(f"[green]✓[/green] Wrote {master}")
        return master
    return out_dir / f"synthesis_batch_1{suffix}.md"


def generate_story(
    influencer: InfluencerConfig,
    prompt_name: str,
    settings: ApiSettings,
    extra_context_files: list[Path] | None = None,
    lang: str = "fa",
) -> Path:
    lang = normalize_lang(lang)
    suffix = lang_suffix(lang)
    out_dir = influencer.stories_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_text = inject_language(load_prompt(prompt_name, influencer), lang)
    parts = [influencer.build_context_block()]
    for path in extra_context_files or []:
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    parts.append(prompt_text)

    llm = make_llm(
        ApiSettings(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=settings.model,
            synthesis_model=settings.model,
            max_workers=1,
        ),
        temperature=influencer.defaults.temperature,
        max_tokens=influencer.defaults.max_tokens * 2,
    )
    message = HumanMessage(content="\n\n---\n\n".join(parts))
    response = llm.invoke([message])

    existing = sorted(out_dir.glob(f"{prompt_name}-*{suffix}.md"))
    next_index = len(existing) + 1
    output_file = out_dir / f"{prompt_name}-{next_index:03d}{suffix}.md"
    output_file.write_text(
        f"# {prompt_name} — {influencer.display_name}\n\n"
        f"**Model:** {settings.model}\n**Language:** {lang}\n\n{response.content}",
        encoding="utf-8",
    )
    console.print(f"[green]✓[/green] Wrote {output_file}")
    return output_file
