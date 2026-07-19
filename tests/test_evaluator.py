from dataclasses import dataclass, field

import pytest

from prompt_registry import evaluator
from prompt_registry.errors import AdapterError, NotFoundError, ValidationError
from prompt_registry.models import CheckSpec


@dataclass
class FakeAdapter:
    """In-memory ModelAdapter: records rendered prompts, returns canned output."""

    output: str = "Summary present, definitely long enough."
    fail_after: int | None = None  # raise AdapterError on the Nth call (1-based)
    name: str = "fake:test"
    prompts: list = field(default_factory=list)

    def generate(self, prompt_text: str) -> str:
        self.prompts.append(prompt_text)
        if self.fail_after is not None and len(self.prompts) >= self.fail_after:
            raise AdapterError("fake adapter failure")
        return self.output


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


class TestAdapterRun:
    def test_renders_per_case_and_records(self, store, cases):
        adapter = FakeAdapter(output="## Summary all good and long enough")
        run, results = evaluator.execute_adapter_run(
            store, "code-review", adapter, note="local gemma",
        )
        # one generation per case, each with the case's variables rendered in
        assert len(adapter.prompts) == 3
        assert all("print(1)" in p for p in adapter.prompts)
        assert all("{{" not in p for p in adapter.prompts)

        by_name = {r.evaluation.case.name: r for r in results}
        assert by_name["structure"].evaluation.passed is True
        assert by_name["manual-only"].evaluation.passed is None
        assert by_name["structure"].output == adapter.output

        assert run.output_source == "fake:test"
        assert store.list_runs("code-review")[0].note == "local gemma"
        assert len(store.get_results(run.id)) == 3

    def test_case_selection(self, store, cases):
        adapter = FakeAdapter()
        _, results = evaluator.execute_adapter_run(
            store, "code-review", adapter, case_names=["length"],
        )
        assert [r.evaluation.case.name for r in results] == ["length"]
        assert len(adapter.prompts) == 1

    def test_adapter_failure_aborts_atomically(self, store, cases):
        adapter = FakeAdapter(fail_after=2)
        with pytest.raises(AdapterError, match="fake adapter failure"):
            evaluator.execute_adapter_run(store, "code-review", adapter)
        # nothing was recorded even though case 1 generated fine
        assert store.list_runs("code-review") == []

    def test_render_failure_aborts_before_generation(self, store, cases):
        from prompt_registry.errors import RenderError
        from prompt_registry.models import VariableSpec

        # new version adds a required variable the old cases don't provide
        store.add_version(
            "code-review", "v2 {{ code }} {{ audience }}",
            (VariableSpec(name="code"), VariableSpec(name="audience")),
        )
        adapter = FakeAdapter()
        with pytest.raises(RenderError, match="audience"):
            evaluator.execute_adapter_run(store, "code-review", adapter)
        assert adapter.prompts == []
        assert store.list_runs("code-review") == []

    def test_run_pins_requested_version(self, store, cases):
        from prompt_registry.models import VariableSpec
        store.add_version("code-review", "v2 {{ code }}", (VariableSpec(name="code"),))
        adapter = FakeAdapter()
        run, _ = evaluator.execute_adapter_run(
            store, "code-review", adapter, version=1, case_names=["manual-only"],
        )
        assert run.prompt_version == 1
        # and the v1 body (with tone default) is what was rendered
        assert "strict" in adapter.prompts[0]

    def test_bad_rating_rejected(self, store, cases):
        with pytest.raises(ValidationError, match="between 1 and 5"):
            evaluator.execute_adapter_run(store, "code-review", FakeAdapter(), rating=0)

    def test_no_cases_is_an_error(self, store, sample_prompt):
        adapter = FakeAdapter()
        with pytest.raises(NotFoundError, match="no eval cases"):
            evaluator.execute_adapter_run(store, "code-review", adapter)
        assert adapter.prompts == []
