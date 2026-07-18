import pytest

from prompt_registry.errors import (
    AlreadyExistsError,
    NotFoundError,
    StorageError,
    ValidationError,
)
from prompt_registry.models import CheckSpec, EvalResult, EvalRun, VariableSpec, new_id, utc_now
from prompt_registry.store import RegistryStore


class TestLifecycle:
    def test_create_then_open(self, tmp_path):
        path = tmp_path / "r.db"
        RegistryStore.create(path).close()
        with RegistryStore.open(path) as store:
            assert store.list_prompts() == []

    def test_create_twice_rejected(self, tmp_path):
        path = tmp_path / "r.db"
        RegistryStore.create(path).close()
        with pytest.raises(AlreadyExistsError):
            RegistryStore.create(path)

    def test_open_missing_rejected(self, tmp_path):
        with pytest.raises(StorageError, match="run 'prompt-registry init'"):
            RegistryStore.open(tmp_path / "nope.db")

    def test_open_non_registry_file_rejected(self, tmp_path):
        path = tmp_path / "junk.db"
        path.write_text("not a database")
        with pytest.raises(StorageError):
            RegistryStore.open(path)


class TestPrompts:
    def test_create_and_get(self, store, sample_prompt):
        prompt, version = sample_prompt
        assert prompt.id == "code-review"
        assert prompt.tags == ("dev", "review")
        assert prompt.latest_version == 1
        assert version.content_hash == store.get_version("code-review").content_hash

    def test_duplicate_id_rejected(self, store, sample_prompt):
        with pytest.raises(AlreadyExistsError):
            store.create_prompt("code-review", "x", "", "body", ())

    def test_invalid_slug_rejected(self, store):
        with pytest.raises(ValidationError, match="invalid prompt id"):
            store.create_prompt("Bad Slug!", "x", "", "body", ())

    def test_empty_body_rejected(self, store):
        with pytest.raises(ValidationError, match="body must not be empty"):
            store.create_prompt("p", "p", "", "   ", ())

    def test_template_schema_mismatch_rejected(self, store):
        with pytest.raises(ValidationError, match="not declared"):
            store.create_prompt("p", "p", "", "hi {{ x }}", ())

    def test_get_unknown_prompt(self, store):
        with pytest.raises(NotFoundError):
            store.get_prompt("ghost")

    def test_tags_normalized_lowercase(self, store):
        store.create_prompt("p", "p", "", "body", (), tags=["DEV", "dev"])
        assert store.get_prompt("p").tags == ("dev",)


class TestVersions:
    def test_add_version_increments(self, store, sample_prompt):
        v2 = store.add_version(
            "code-review",
            "Review {{ code }} carefully.",
            (VariableSpec(name="code"),),
            note="dropped tone",
        )
        assert v2.version == 2
        assert store.get_prompt("code-review").latest_version == 2
        assert store.get_version("code-review").version == 2
        assert store.get_version("code-review", 1).body.startswith("Review {{ code }} with")

    def test_identical_version_rejected(self, store, sample_prompt):
        _, v1 = sample_prompt
        with pytest.raises(ValidationError, match="identical to v1"):
            store.add_version("code-review", v1.body, v1.variables)

    def test_versions_are_immutable_append_only(self, store, sample_prompt):
        store.add_version("code-review", "v2 {{ code }}", (VariableSpec(name="code"),))
        versions = store.list_versions("code-review")
        assert [v.version for v in versions] == [1, 2]

    def test_missing_version(self, store, sample_prompt):
        with pytest.raises(NotFoundError, match="version 99"):
            store.get_version("code-review", 99)


class TestSearchAndList:
    @pytest.fixture(autouse=True)
    def corpus(self, store):
        store.create_prompt("debug-helper", "Debugger", "find bugs", "Debug: {{ err }}",
                            (VariableSpec(name="err"),), tags=["dev"])
        store.create_prompt("handoff", "Handoff", "project handoff notes",
                            "Summarize the project state.", (), tags=["ops"])

    def test_list_all(self, store):
        assert [p.id for p in store.list_prompts()] == ["debug-helper", "handoff"]

    def test_list_by_tag(self, store):
        assert [p.id for p in store.list_prompts(tag="ops")] == ["handoff"]

    def test_search_body(self, store):
        assert [p.id for p in store.search_prompts("Summarize")] == ["handoff"]

    def test_search_name_and_description(self, store):
        assert [p.id for p in store.search_prompts("bugs")] == ["debug-helper"]

    def test_search_by_tag_text(self, store):
        assert [p.id for p in store.search_prompts("ops")] == ["handoff"]

    def test_search_with_tag_filter(self, store):
        assert store.search_prompts("project", tag="dev") == []
        assert [p.id for p in store.search_prompts("project", tag="ops")] == ["handoff"]

    def test_search_searches_latest_body_only(self, store):
        store.add_version("handoff", "Completely new body.", ())
        assert store.search_prompts("Summarize") == []
        assert [p.id for p in store.search_prompts("Completely new")] == ["handoff"]

    def test_like_wildcards_are_escaped(self, store):
        assert store.search_prompts("%") == []
        assert store.search_prompts("_") == []


class TestTags:
    def test_add_and_remove(self, store, sample_prompt):
        store.add_tags("code-review", ["Extra"])
        assert "extra" in store.get_prompt("code-review").tags
        store.remove_tags("code-review", ["extra", "dev"])
        assert store.get_prompt("code-review").tags == ("review",)

    def test_invalid_tag_rejected(self, store, sample_prompt):
        with pytest.raises(ValidationError, match="invalid tag"):
            store.add_tags("code-review", ["bad tag!"])


class TestCases:
    def test_add_and_get(self, store, sample_prompt):
        case = store.add_case(
            "code-review", "smoke",
            {"code": "print(1)"},
            (CheckSpec(type="contains", params={"value": "print"}),),
        )
        loaded = store.get_case("code-review", "smoke")
        assert loaded.id == case.id
        assert loaded.variables == {"code": "print(1)"}
        assert loaded.checks[0].type == "contains"

    def test_duplicate_name_rejected(self, store, sample_prompt):
        store.add_case("code-review", "smoke", {}, ())
        with pytest.raises(AlreadyExistsError):
            store.add_case("code-review", "smoke", {}, ())

    def test_bad_check_rejected_at_write_time(self, store, sample_prompt):
        with pytest.raises(ValidationError, match="unknown check type"):
            store.add_case("code-review", "bad", {}, (CheckSpec(type="magic"),))

    def test_unknown_case(self, store, sample_prompt):
        with pytest.raises(NotFoundError):
            store.get_case("code-review", "ghost")


class TestRuns:
    def test_record_and_read_back(self, store, sample_prompt):
        case = store.add_case("code-review", "smoke", {"code": "x"}, ())
        run = EvalRun(
            id=new_id(), prompt_id="code-review", prompt_version=1,
            note="manual", output_source="stdin", created_at=utc_now(),
        )
        result = EvalResult(
            run_id=run.id, case_id=case.id, passed=True,
            details=({"type": "contains", "passed": True, "message": "ok"},),
            rating=4, comment="good",
        )
        store.record_run(run, [result])

        runs = store.list_runs("code-review")
        assert len(runs) == 1 and runs[0].id == run.id
        results = store.get_results(run.id)
        assert len(results) == 1
        loaded, case_name = results[0]
        assert case_name == "smoke"
        assert loaded.passed is True
        assert loaded.rating == 4
        assert loaded.details[0]["type"] == "contains"

    def test_null_passed_round_trips(self, store, sample_prompt):
        case = store.add_case("code-review", "manual-only", {"code": "x"}, ())
        run = EvalRun(id=new_id(), prompt_id="code-review", prompt_version=1,
                      note="", output_source="", created_at=utc_now())
        store.record_run(run, [EvalResult(run_id=run.id, case_id=case.id,
                                          passed=None, details=(), rating=5)])
        loaded, _ = store.get_results(run.id)[0]
        assert loaded.passed is None
        assert loaded.rating == 5
