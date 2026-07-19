# prompt-registry

A local-first prompt registry and evaluator. Store, version, tag, search,
render, diff, and evaluate prompts as first-class assets — instead of losing
them in chat history.

- **Local only.** One SQLite file. No cloud, no accounts, no paid APIs. Works
  fully offline.
- **Model-agnostic.** Outputs are produced wherever you like (Claude Code, a
  local Gemma via Ollama, anything) and fed back in for evaluation — or, since
  v0.2, generated in one command through a local Ollama server.
- **Zero runtime dependencies.** Pure Python 3.10+ standard library. pytest is
  the only dev dependency.
- **Versions are immutable.** Every change to a prompt appends a new numbered
  version with a content hash; nothing is ever edited in place, so every
  evaluation is pinned to the exact text it ran against.

## Install

```bash
pip install -e .            # from the repo root
pip install -e '.[dev]'     # with pytest, to run the tests
```

This installs the `prompt-registry` command (also runnable as
`python -m prompt_registry`).

## Quick start

```bash
# 1. Create the registry (default: ~/.prompt-registry/registry.db)
prompt-registry init

# 2. Store a prompt. {{ placeholders }} become variables automatically;
#    --var NAME is required, --var NAME=DEFAULT is optional with a default.
cat > review.txt <<'EOF'
You are a code reviewer.
Review:
{{ code }}

Respond with a section titled "## Summary" and severity {{ severity }}.
EOF
prompt-registry add code-review --name "Code Review" \
    --body-file review.txt --var code --var "severity=medium" \
    --tag dev --tag review

# 3. Find and inspect prompts
prompt-registry list --tag dev
prompt-registry search "reviewer"
prompt-registry show code-review

# 4. Render with variables (pipe straight into your model of choice)
prompt-registry render code-review --var "code=$(cat mymodule.py)"

# 5. Evolve it — every change is a new immutable version
prompt-registry new-version code-review --body-file review-v2.txt \
    --note "tightened summary format"
prompt-registry diff code-review          # previous vs latest
prompt-registry diff code-review 1 3      # any two versions
prompt-registry versions code-review

# 6. Attach an eval case: variables + deterministic checks
prompt-registry case add code-review structure \
    --var "code=def f(): pass" \
    --check "contains:## Summary" \
    --check "not_contains:apologize" \
    --check "min_length:20"

# 7a. Manual loop: run the prompt anywhere, capture the output, evaluate it
prompt-registry render code-review --var "code=def f(): pass" -o input.txt
# ... run input.txt through Claude Code / Gemma / anything, save to out.txt ...
prompt-registry eval run code-review --output-file out.txt \
    --rating 4 --note "claude code, manual"

# 7b. One-command local loop (optional, requires Ollama): render each case,
#     generate through a local model, check, record
prompt-registry eval run code-review --model gemma3 --note "gemma3 local"

# 8. Review the evidence
prompt-registry eval history code-review --detail
```

`eval run` exits 0 when all checked cases pass and 1 otherwise, so it can gate
scripts.

## Optional: local model execution via Ollama

Everything above works fully offline with no model server. If you also want
the one-command loop, install [Ollama](https://ollama.com) and pull a model:

```bash
ollama pull gemma3        # or gemma2:2b, llama3.2, qwen2.5-coder, ...
ollama serve              # usually already running as a service
prompt-registry eval run code-review --model gemma3
```

With `--model`, each selected case is rendered with its own variables, sent to
Ollama's `/api/generate`, and the generated output is checked and recorded —
one output per case, pinned to the exact prompt version. Flags:

- `--model NAME` — required to enable adapter mode; any Ollama model name.
- `--ollama-url URL` — default `$OLLAMA_HOST` or `http://localhost:11434`.
- `--timeout SECONDS` — per-case generation timeout (default 120).
- `--temperature F` — default `0.0` so re-runs are as deterministic as the
  model allows.
- `--show-output` — print each generated output. By default outputs stay
  in-memory only: they are never stored in the registry and never logged.

Failure behavior is explicit and atomic: if Ollama is unreachable, the model
isn't pulled, the request times out, or the response is malformed, the command
exits 1 with an actionable message and **no partial eval run is recorded**.
Only `eval run --model` ever touches the network; every other command works
without Ollama installed.

## Where data lives

Resolution order for the database path:

1. `--db PATH` flag
2. `PROMPT_REGISTRY_DB` environment variable
3. `~/.prompt-registry/registry.db`

Back up the registry by copying that one file.

## Concepts

| Entity | What it is |
| --- | --- |
| Prompt | A named asset with an id (slug), description, and tags. |
| PromptVersion | Immutable numbered snapshot: body + variable schema + note + SHA-256 content hash. |
| VariableSpec | One `{{ placeholder }}`: required (must be supplied) or optional (has a default). The schema is stored on the version, so the contract travels with the text. |
| EvalCase | Named inputs (variable values) plus deterministic checks, attached to a prompt. |
| EvalRun / EvalResult | One evaluation of a captured output against cases, pinned to an exact prompt version. Model outputs themselves are not stored. |

### Check types

`contains`, `not_contains` (optional `case_sensitive: false` via
`--checks-file`), `regex`, `not_regex` (multiline), `is_json`, `min_length`,
`max_length`. All deterministic — no LLM judges in v1.

### Rendering rules (strict on purpose)

- Only well-formed `{{ name }}` is a placeholder; JSON braces and code in
  prompt bodies are left untouched.
- Every placeholder must be declared, every declared variable must be used —
  enforced when the version is written.
- Rendering fails loudly on missing required variables or unknown values.
- Substitution is single-pass; values are never re-expanded.
- Variable values and model outputs are never logged.

## Development

```bash
pip install -e '.[dev]'
pytest -q
```

Layout: `src/prompt_registry/` — `models.py` (frozen dataclasses),
`store.py` (all SQLite persistence, no CLI coupling), `rendering.py`,
`checks.py`, `diffing.py`, `evaluator.py`, `adapters.py` (the model-adapter
seam: `ManualAdapter` and the stdlib-only `OllamaAdapter`), `cli.py`.
Tests stub Ollama with a local `http.server`; no test needs Ollama installed.

## Deliberately not built yet

An MCP read-only server for Claude Code, full-text search, import/export,
judge-model evals, retries/concurrency for generation, output persistence,
any UI. The storage layer is CLI-independent, so the MCP surface can be added
without touching the core.
