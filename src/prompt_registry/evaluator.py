"""Evaluation runner: apply a prompt's eval cases to a captured output and
record the results against the exact prompt version, so every evaluation is
reproducible after the fact."""

from __future__ import annotations

from dataclasses import dataclass

from .checks import CheckOutcome, run_check
from .errors import NotFoundError, ValidationError
from .models import EvalCase, EvalResult, EvalRun, new_id, utc_now
from .store import RegistryStore


@dataclass(frozen=True)
class CaseEvaluation:
    case: EvalCase
    passed: bool | None  # None: case has no automated checks
    outcomes: tuple[CheckOutcome, ...]


def evaluate_case(case: EvalCase, output: str) -> CaseEvaluation:
    outcomes = tuple(run_check(spec, output) for spec in case.checks)
    passed = all(o.passed for o in outcomes) if outcomes else None
    return CaseEvaluation(case=case, passed=passed, outcomes=outcomes)


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
    """Evaluate an output against selected (default: all) cases and persist.

    The output text itself is intentionally NOT stored: eval records stay
    small and cannot leak sensitive model output; reproduce by re-running
    the same version + case elsewhere.
    """
    if rating is not None and not 1 <= rating <= 5:
        raise ValidationError("rating must be between 1 and 5")

    prompt_version = store.get_version(prompt_id, version)

    if case_names:
        unique_names = list(dict.fromkeys(case_names))
        cases = [store.get_case(prompt_id, name) for name in unique_names]
    else:
        cases = store.list_cases(prompt_id)
        if not cases:
            raise NotFoundError(
                f"prompt '{prompt_id}' has no eval cases; "
                f"add one with 'prompt-registry case add'"
            )

    evaluations = [evaluate_case(case, output) for case in cases]

    run = EvalRun(
        id=new_id(),
        prompt_id=prompt_id,
        prompt_version=prompt_version.version,
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
    return run, evaluations
