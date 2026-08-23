from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from rich.console import Console

from persona_studio.config import InfluencerConfig
from persona_studio.language import inject_language, lang_suffix, normalize_lang
from persona_studio.prompts import list_images, load_prompt
from persona_studio.settings import ApiSettings, make_llm
from persona_studio.ui.progress import live_progress

console = Console()

_MIME = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".gif": "gif",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".webp": "webp",
}


class ImageAnalysisState(TypedDict):
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
        _MIME.get(suffix, "jpeg"),
    )


def build_workflow() -> StateGraph:
    workflow = StateGraph(ImageAnalysisState)

    def analyze_image_node(state: ImageAnalysisState) -> ImageAnalysisState:
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
            message = HumanMessage(
                content=[
                    {"type": "text", "text": state["prompt"]},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{state['mime']};base64,{state['image_base64']}",
                            "detail": "high",
                        },
                    },
                ]
            )
            response = llm.invoke([message])
            state["analysis_result"] = response.content
            state["error"] = None
        except Exception as exc:
            state["analysis_result"] = f"Error analyzing image: {exc}"
            state["error"] = str(exc)
        return state

    workflow.add_node("analyze", analyze_image_node)
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
) -> dict[str, dict[str, Any]]:
    lang = normalize_lang(lang)
    suffix = lang_suffix(lang)
    source_dir = images_dir or influencer.images_dir()
    out_dir = output_dir or influencer.reports_dir() / prompt_name
    images = list_images(source_dir)
    if not images:
        console.print(f"[yellow]No image files found in {source_dir}[/yellow]")
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
    graph = build_workflow().compile(checkpointer=MemorySaver())
    results: dict[str, dict[str, Any]] = {}

    def analyze_one(image_path: Path) -> dict[str, Any]:
        b64, mime = encode_image(image_path)
        state: ImageAnalysisState = {
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
        result = graph.invoke(state, {"configurable": {"thread_id": image_path.name}})
        return result

    with live_progress(len(images), title=f"Analyzing {len(images)} images ({settings.model})") as advance:
        with ThreadPoolExecutor(max_workers=settings.max_workers) as executor:
            futures = {executor.submit(analyze_one, img): img for img in images}
            for future in as_completed(futures):
                image_path = futures[future]
                try:
                    result = future.result()
                    analysis = result["analysis_result"]
                    error = result.get("error")
                    output_file = out_dir / f"{image_path.stem}{suffix}.md"
                    header = (
                        f"# Analysis of {image_path.name}\n\n"
                        f"**Influencer:** {influencer.display_name}\n"
                        f"**Image Path:** {image_path}\n"
                        f"**Model Used:** {settings.model}\n"
                        f"**Prompt:** {prompt_name}\n"
                        f"**Language:** {lang}\n"
                        f"**Workflow:** LangGraph\n\n"
                        f"## Analysis Result\n\n"
                    )
                    output_file.write_text(header + analysis, encoding="utf-8")
                    results[image_path.name] = {
                        "status": "error" if error else "success",
                        "output_file": str(output_file),
                    }
                except Exception as exc:
                    results[image_path.name] = {"status": "error", "error": str(exc)}
                advance()

    return results
