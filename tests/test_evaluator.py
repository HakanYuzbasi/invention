import pytest

from prompt_registry import evaluator
from prompt_registry.errors import NotFoundError, ValidationError
from prompt_registry.models import CheckSpec


@pytest.fixture
def cases(store, sample_prompt):
    store.add_case(
        "code-review", "structure",
        {"code": "print(1)"},
        (
            CheckSpec(type="contains", params={"value": "Summary"}),
            CheckSpec(type="not_contains", params={"value": "apologize"}),
        ),
    )
    store.add_case(
        "code-review", "length",
        {"code": "print(1)"},
        (CheckSpec(type="min_length", params={"value": 10}),),
    )
    store.add_case("code-review", "manual-only", {"code": "print(1)"}, ())


def test_run_all_cases_and_persist(store, cases):
    run, evaluations = evaluator.execute_run(
        store, "code-review",
        output="Summary: looks fine, long enough output.",
        output_source="file:out.txt", note="gemma-2b",
    )
    by_name = {ev.case.name: ev for ev in evaluations}
    assert by_name["structure"].passed is True
    assert by_name["length"].passed is True
    assert by_name["manual-only"].passed is None

    persisted = store.get_results(run.id)
    assert len(persisted) == 3
    assert store.list_runs("code-review")[0].note == "gemma-2b"


def test_failing_check_marks_case_failed(store, cases):
    _, evaluations = evaluator.execute_run(
        store, "code-review", output="I apologize. Summary here, long enough.",
    )
    by_name = {ev.case.name: ev for ev in evaluations}
    assert by_name["structure"].passed is False
    failed = [o for o in by_name["structure"].outcomes if not o.passed]
    assert failed[0].type == "not_contains"


def test_select_specific_case(store, cases):
    _, evaluations = evaluator.execute_run(
        store, "code-review", output="whatever", case_names=["length"],
    )
    assert [ev.case.name for ev in evaluations] == ["length"]


def test_duplicate_case_names_deduped(store, cases):
    run, evaluations = evaluator.execute_run(
        store, "code-review", output="whatever", case_names=["length", "length"],
    )
    assert len(evaluations) == 1
    assert len(store.get_results(run.id)) == 1


def test_no_cases_is_an_error(store, sample_prompt):
    with pytest.raises(NotFoundError, match="no eval cases"):
        evaluator.execute_run(store, "code-review", output="x")


def test_unknown_case_is_an_error(store, cases):
    with pytest.raises(NotFoundError, match="'ghost' not found"):
        evaluator.execute_run(store, "code-review", output="x", case_names=["ghost"])


def test_bad_rating_rejected(store, cases):
    with pytest.raises(ValidationError, match="between 1 and 5"):
        evaluator.execute_run(store, "code-review", output="x", rating=9)


def test_run_pins_prompt_version(store, cases):
    from prompt_registry.models import VariableSpec
    store.add_version("code-review", "v2 {{ code }}", (VariableSpec(name="code"),))
    run_v1, _ = evaluator.execute_run(store, "code-review", output="x",
                                      version=1, case_names=["manual-only"])
    run_latest, _ = evaluator.execute_run(store, "code-review", output="x",
                                          case_names=["manual-only"])
    assert run_v1.prompt_version == 1
    assert run_latest.prompt_version == 2
