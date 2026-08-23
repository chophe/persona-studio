# persona-studio

Config-driven influencer persona pipeline. Add a new influencer by dropping a
folder under `influencers/` — the code stays generic.

Generalized from `influencer-rp` / `influencer-rp`: same LangGraph + OpenAI-compatible stack,
but personas, portraits, and special prompts are pure configuration.

## Layout

```
persona-studio/
├── prompts/                  # shared prompt library (markdown, with [ref](path) inlining)
├── influencers/
│   ├── _template/            # copy this to start a new persona
│   │   ├── config.yaml       # name, handle, portrait, defaults, paths, special_prompts
│   │   ├── persona.md        # central personal description
│   │   └── special/          # extra context blocks injected into every request
│   └── <slug>/
└── src/persona_studio/
    ├── config.py             # YAML config loading + validation (pydantic)
    ├── prompts.py            # prompt loader with markdown reference inlining
    ├── settings.py           # env/CLI API settings → ChatOpenAI factory
    ├── image_analyzer.py     # LangGraph batch image analysis
    ├── story.py              # report synthesis + story/RP generation
    └── cli.py                # Typer CLI
```

## Setup

```bash
cd persona_studio
uv sync
cp .env.template .env   # then fill in OPENAI_API_KEY / OPENAI_BASE_URL / MODEL_NAME
uv run persona-studio --help
```

Works with any OpenAI-compatible endpoint (OpenAI, Gemini via proxy like avalai,
etc.) — set `OPENAI_BASE_URL` accordingly.

## Adding an influencer

```bash
uv run persona-studio init example-influencer --name "Example Influencer" --handle "@example"
```

Then edit `influencers/example-influencer/config.yaml`, `persona.md`, and files in
`special/`. Drop screenshots into `images/` and (optionally) a `portrait.jpg`.

Per-influencer prompt overrides: put `<prompt>.md` inside
`influencers/<slug>/prompts/` — it shadows the shared one.

## Usage

```bash
# list / inspect
uv run persona-studio personas
uv run persona-studio show example-influencer
uv run persona-studio prompts example-influencer

# stage 1: analyze screenshots -> per-image markdown reports
uv run persona-studio analyze example-influencer human-level-interpretation

# override folders/model for a run
uv run persona-studio analyze example-influencer fashion-extraction \
  --images ./new_batch --out ./out/batch1 --model gemini-2.5-flash

# stage 2: synthesize reports into narrative summaries
uv run persona-studio synthesize example-influencer task3(a)-longitudinal-biography \
  influencers/example-influencer/output/reports/human-level-interpretation

# stage 3: generate stories / RP content from persona + prompt
uv run persona-studio story example-influencer task3(c)-story
uv run persona-studio story example-influencer task3(b)-rp-character \
  --context influencers/example-influencer/output/syntheses/task3(a)-longitudinal-biography/master_synthesis.md
```

Persona text, special-prompt blocks, and handle are automatically prepended as
context to every analysis and story request.

## Tests

```bash
uv run pytest
```
