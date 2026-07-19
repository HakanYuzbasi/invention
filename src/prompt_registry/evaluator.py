"""Evaluation runner: apply a prompt's eval cases to model output and record
the results against the exact prompt version, so every evaluation is
reproducible after the fact.

Two entry points:
- execute_run: the v1 manual loop — ONE captured output, evaluated against
  the selected cases.
- execute_adapter_run: the v2 automated loop — each case's variables are
  rendered against the pinned version and sent through a ModelAdapter,
  producing one output per case.

In both modes the model output itself is intentionally NOT stored: eval
records stay small and cannot leak sensitive output; reproduce by re-running
the same version + case.
"""

from __future__ import annotations

from dataclasses import dataclass

from .adapters import ModelAdapter
from .checks import CheckOutcome, run_check
from .errors import NotFoundError, ValidationError
from .models import EvalCase, EvalResult, EvalRun, new_id, utc_now
from .rendering import render
from .store import RegistryStore


@dataclass(frozen=True)
class CaseEvaluation:
    case: EvalCase
    passed: bool | None  # None: case has no automated checks
    outcomes: tuple[CheckOutcome, ...]


@dataclass(frozen=True)
class AdapterCaseResult:
    """One case's adapter-mode result; output lives in memory only."""

    evaluation: CaseEvaluation
    output: str


def evaluate_case(case: EvalCase, output: str) -> CaseEvaluation:
    outcomes = tuple(run_check(spec, output) for spec in case.checks)
    passed = all(o.passed for o in outcomes) if outcomes else None
    return CaseEvaluation(case=case, passed=passed, outcomes=outcomes)


def _validate_rating(rating: int | None) -> None:
    if rating is not None and not 1 <= rating <= 5:
        raise ValidationError("rating must be between 1 and 5")


def _select_cases(
    store: RegistryStore, prompt_id: str, case_names: list[str] | None
) -> list[EvalCase]:
    if case_names:
        unique_names = list(dict.fromkeys(case_names))
        return [store.get_case(prompt_id, name) for name in unique_names]
    cases = store.list_cases(prompt_id)
    if not cases:
        raise NotFoundError(
            f"prompt '{prompt_id}' has no eval cases; "
            f"add one with 'prompt-registry case add'"
        )
    return cases


def _record(
    store: RegistryStore,
    prompt_id: str,
    prompt_version: int,
    evaluations: list[CaseEvaluation],
    output_source: str,
    note: str,
    rating: int | None,
    comment: str,
) -> EvalRun:
    run = EvalRun(
        id=new_id(),
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        note=note,
        output_source=output_source,
        created_at=utc_now(),
    )
    results = [
        EvalResult(
            run_id=run.id,
            case_id=ev.case.id,
            passed=ev.passed,
            details=tuple(o.to_dict() for o in ev.outcomes),
            rating=rating,
            comment=comment,
        )
        for ev in evaluations
    ]
    store.record_run(run, results)
    return run


def execute_run(
    store: RegistryStore,
    prompt_id: str,
    output: str,
    version: int | None = None,
    case_names: list[str] | None = None,
    output_source: str = "",
    note: str = "",
    rating: int | None = None,
    comment: str = "",
) -> tuple[EvalRun, list[CaseEvaluation]]:
    """Manual mode: evaluate ONE captured output against selected cases."""
    _validate_rating(rating)
    prompt_version = store.get_version(prompt_id, version)
    cases = _select_cases(store, prompt_id, case_names)
    evaluations = [evaluate_case(case, output) for case in cases]
    run = _record(
        store, prompt_id, prompt_version.version, evaluations,
        output_source, note, rating, comment,
    )
    return run, evaluations


def execute_adapter_run(
    store: RegistryStore,
    prompt_id: str,
    adapter: ModelAdapter,
    version: int | None = None,
    case_names: list[str] | None = None,
    note: str = "",
    rating: int | None = None,
    comment: str = "",
) -> tuple[EvalRun, list[AdapterCaseResult]]:
    """Adapter mode: render each case, generate an output per case, evaluate.

    Atomic on failure: if rendering or generation fails for ANY case, the
    whole run aborts before anything is recorded — no partial eval runs.
    """
    _validate_rating(rating)
    prompt_version = store.get_version(prompt_id, version)
    cases = _select_cases(store, prompt_id, case_names)

    case_results: list[AdapterCaseResult] = []
    for case in cases:
        rendered = render(
            prompt_version.body, prompt_version.variables, dict(case.variables)
        )
        output = adapter.generate(rendered)
        case_results.append(AdapterCaseResult(evaluate_case(case, output), output))

    run = _record(
        store, prompt_id, prompt_version.version,
        [r.evaluation for r in case_results],
        adapter.name, note, rating, comment,
    )
    return run, case_results
