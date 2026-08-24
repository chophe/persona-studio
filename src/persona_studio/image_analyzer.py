from __future__ import annotations

import base64
import errno
import fcntl
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from rich.console import Console

from persona_studio.config import InfluencerConfig
from persona_studio.language import inject_language, lang_suffix, normalize_lang
from persona_studio.prompts import list_images, list_videos, load_prompt
from persona_studio.settings import ApiSettings, make_llm
from persona_studio.ui.progress import live_progress

console = Console()

_IMAGE_MIME = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".gif": "gif",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".webp": "webp",
}

_VIDEO_MIME = {
    ".mp4": "mp4",
    ".mov": "quicktime",
    ".mkv": "x-matroska",
    ".avi": "x-msvideo",
    ".webm": "webm",
    ".m4v": "mp4",
    ".flv": "x-flv",
    ".wmv": "x-ms-wmv",
    ".mpg": "mpeg",
    ".mpeg": "mpeg",
}


class ImageAnalysisState(TypedDict):
    media: str
    image_base64: str
    mime: str
    prompt: str
    model_name: str
    base_url: str
    api_key: str
    max_tokens: int
    temperature: float
    analysis_result: str
    error: str | None


def encode_image(image_path: Path) -> tuple[str, str]:
    suffix = image_path.suffix.lower()
    return (
        base64.b64encode(image_path.read_bytes()).decode("utf-8"),
        _IMAGE_MIME.get(suffix, "jpeg"),
    )


def encode_video(video_path: Path) -> tuple[str, str]:
    suffix = video_path.suffix.lower()
    return (
        base64.b64encode(video_path.read_bytes()).decode("utf-8"),
        _VIDEO_MIME.get(suffix, "mp4"),
    )


def _has_error(output_file: Path) -> bool:
    """True when an existing report looks like a failed analysis (should be re-run)."""
    try:
        return "Error analyzing" in output_file.read_text(encoding="utf-8")
    except OSError:
        return True


def _is_done(output_file: Path) -> bool:
    """True when the report already contains a successful analysis (skip it)."""
    try:
        return output_file.stat().st_size > 0 and not _has_error(output_file)
    except OSError:
        return False


@contextmanager
def _exclusive_lock(output_file: Path) -> Iterator[bool]:
    """Acquire a non-blocking exclusive lock on the report file.

    Yields True when this process holds the lock (and may proceed), False when
    another process already holds it (the caller should skip). The lock is
    released automatically when the context exits or the process exits.
    """
    fd = os.open(str(output_file), os.O_RDWR | os.O_CREAT)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                yield False
                return
            raise
        yield True
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def build_workflow() -> StateGraph:
    workflow = StateGraph(ImageAnalysisState)

    def analyze_media_node(state: ImageAnalysisState) -> ImageAnalysisState:
        try:
            llm = make_llm(
                ApiSettings(
                    api_key=state["api_key"],
                    base_url=state["base_url"],
                    model=state["model_name"],
                    synthesis_model=state["model_name"],
                    max_workers=1,
                ),
                temperature=state["temperature"],
                max_tokens=state["max_tokens"],
            )
            if state["media"] == "video":
                media_block = {
                    "type": "video_url",
                    "video_url": {
                        "url": f"data:video/{state['mime']};base64,{state['image_base64']}"
                    },
                }
            else:
                media_block = {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{state['mime']};base64,{state['image_base64']}",
                        "detail": "high",
                    },
                }
            message = HumanMessage(
                content=[
                    {"type": "text", "text": state["prompt"]},
                    media_block,
                ]
            )
            response = llm.invoke([message])
            state["analysis_result"] = response.content
            state["error"] = None
        except Exception as exc:
            state["analysis_result"] = f"Error analyzing: {exc}"
            state["error"] = str(exc)
        return state

    workflow.add_node("analyze", analyze_media_node)
    workflow.add_edge("analyze", END)
    workflow.set_entry_point("analyze")
    return workflow


def run_analysis(
    influencer: InfluencerConfig,
    prompt_name: str,
    settings: ApiSettings,
    images_dir: Path | None = None,
    output_dir: Path | None = None,
    include_persona: bool = True,
    lang: str = "fa",
    rewrite: bool = False,
    media: str = "image",
) -> dict[str, dict[str, Any]]:
    lang = normalize_lang(lang)
    suffix = lang_suffix(lang)
    source_dir = images_dir or influencer.images_dir()
    out_dir = output_dir or influencer.reports_dir() / prompt_name
    is_video = media == "video"

    files = list_videos(source_dir) if is_video else list_images(source_dir)
    if not files:
        kind = "video" if is_video else "image"
        console.print(f"[yellow]No {kind} files found in {source_dir}[/yellow]")
        return {}

    prompt_text = load_prompt(prompt_name, influencer)
    if include_persona:
        try:
            context_block = influencer.build_context_block()
            prompt_text = f"{context_block}\n\n---\n\n{prompt_text}"
        except FileNotFoundError:
            console.print("[yellow]Persona file missing; analyzing without persona context.[/yellow]")
    prompt_text = inject_language(prompt_text, lang)

    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}

    def output_file_for(file_path: Path) -> Path:
        return out_dir / f"{file_path.stem}{suffix}.md"

    graph = build_workflow().compile(checkpointer=MemorySaver())

    def analyze_one(file_path: Path) -> dict[str, Any]:
        output_file = output_file_for(file_path)
        with _exclusive_lock(output_file) as locked:
            if not locked:
                return {
                    "status": "skipped",
                    "reason": "locked",
                    "output_file": str(output_file),
                }
            if not rewrite and _is_done(output_file):
                return {
                    "status": "skipped",
                    "reason": "exists",
                    "output_file": str(output_file),
                }

            b64, mime = (encode_video(file_path) if is_video else encode_image(file_path))
            state: ImageAnalysisState = {
                "media": media,
                "image_base64": b64,
                "mime": mime,
                "prompt": prompt_text,
                "model_name": settings.model,
                "base_url": settings.base_url,
                "api_key": settings.api_key,
                "max_tokens": influencer.defaults.max_tokens,
                "temperature": influencer.defaults.temperature,
                "analysis_result": "",
                "error": None,
            }
            result = graph.invoke(state, {"configurable": {"thread_id": file_path.name}})
            analysis = result["analysis_result"]
            error = result.get("error")

            kind = "Video" if is_video else "Image"
            header = (
                f"# Analysis of {file_path.name}\n\n"
                f"**Influencer:** {influencer.display_name}\n"
                f"**{kind} Path:** {file_path}\n"
                f"**Model Used:** {settings.model}\n"
                f"**Prompt:** {prompt_name}\n"
                f"**Language:** {lang}\n"
                f"**Workflow:** LangGraph\n\n"
                f"## Analysis Result\n\n"
            )
            output_file.write_text(header + analysis, encoding="utf-8")
            return {
                "status": "error" if error else "success",
                "output_file": str(output_file),
            }

    with live_progress(
        len(files), title=f"Analyzing {len(files)} {'videos' if is_video else 'images'} ({settings.model})"
    ) as advance:
        with ThreadPoolExecutor(max_workers=settings.max_workers) as executor:
            futures = {executor.submit(analyze_one, f): f for f in files}
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    results[file_path.name] = future.result()
                except Exception as exc:
                    results[file_path.name] = {"status": "error", "error": str(exc)}
                advance()

    return results
