import sqlite3

import pytest

from prompt_registry.errors import NotFoundError, StorageError
from prompt_registry.models import VariableSpec
from prompt_registry.readonly import ReadOnlyRegistry, make_preview
from prompt_registry.store import RegistryStore


def dump(db_path) -> str:
    with sqlite3.connect(str(db_path)) as conn:
        return "\n".join(conn.iterdump())


@pytest.fixture
def seeded_db(tmp_path):
    path = tmp_path / "registry.db"
    with RegistryStore.create(path) as store:
        store.create_prompt(
            "code-review", "Code Review", "reviews code",
            "Review {{ code }} with tone {{ tone }}.",
            (
                VariableSpec(name="code"),
                VariableSpec(name="tone", required=False, default="strict"),
            ),
            tags=["dev", "review"],
        )
        store.add_version(
            "code-review", "Review carefully: {{ code }}",
            (VariableSpec(name="code"),), note="dropped tone",
        )
        store.create_prompt(
            "handoff", "Handoff", "project handoff",
            "Summarize the project state in detail. " * 20, (), tags=["ops"],
        )
    return path


class TestMakePreview:
    def test_collapses_whitespace(self):
        assert make_preview("a\n\n  b\tc") == "a b c"

    def test_truncates_with_ellipsis(self):
        preview = make_preview("word " * 100)
        assert len(preview) <= 160
        assert preview.endswith("…")

    def test_short_body_untouched(self):
        assert make_preview("short body") == "short body"


class TestReadOnlyRegistry:
    def test_open_and_read(self, seeded_db):
        with ReadOnlyRegistry.open(seeded_db) as registry:
            prompt = registry.get_prompt("code-review")
            assert prompt.latest_version == 2
            assert registry.get_version("code-review").version == 2
            assert registry.get_version("code-review", 1).version == 1
            assert [v.version for v in registry.list_versions("code-review")] == [1, 2]

    def test_resolve_by_name_case_insensitive(self, seeded_db):
        with ReadOnlyRegistry.open(seeded_db) as registry:
            assert registry.resolve("code review") == "code-review"
            assert registry.resolve("CODE REVIEW") == "code-review"
            assert registry.resolve("code-review") == "code-review"

    def test_resolve_unknown(self, seeded_db):
        with ReadOnlyRegistry.open(seeded_db) as registry:
            with pytest.raises(NotFoundError, match="no prompt with id or name"):
                registry.resolve("ghost")

    def test_resolve_ambiguous_name(self, tmp_path):
        path = tmp_path / "r.db"
        with RegistryStore.create(path) as store:
            store.create_prompt("a1", "Same Name", "", "body a", ())
            store.create_prompt("a2", "Same Name", "", "body b", ())
        with ReadOnlyRegistry.open(path) as registry:
            with pytest.raises(NotFoundError, match="ambiguous"):
                registry.resolve("same name")

    def test_search_with_preview_and_tag(self, seeded_db):
        with ReadOnlyRegistry.open(seeded_db) as registry:
            results = registry.search("project", tag="ops")
            assert len(results) == 1
            prompt, preview = results[0]
            assert prompt.id == "handoff"
            assert preview.startswith("Summarize the project state")
            assert len(preview) <= 160

    def test_empty_query_lists_all(self, seeded_db):
        with ReadOnlyRegistry.open(seeded_db) as registry:
            assert len(registry.search("")) == 2
            assert len(registry.search("", limit=1)) == 1

    def test_limit_clamped_to_at_least_one(self, seeded_db):
        with ReadOnlyRegistry.open(seeded_db) as registry:
            assert len(registry.search("", limit=0)) == 1
            assert len(registry.search("", limit=10**9)) == 2  # huge limit is safe

    def test_missing_db_raises_storage_error(self, tmp_path):
        with pytest.raises(StorageError, match="prompt-registry init"):
            ReadOnlyRegistry.open(tmp_path / "nope.db")

    def test_no_mutation_methods_exposed(self):
        mutating = [
            name for name in dir(ReadOnlyRegistry)
            if not name.startswith("_")
            and any(verb in name.lower() for verb in
                    ("create", "add", "remove", "delete", "record",
                     "update", "write", "insert", "tag_"))
        ]
        assert mutating == []

    def test_underlying_connection_rejects_writes(self, seeded_db):
        before = dump(seeded_db)
        with ReadOnlyRegistry.open(seeded_db) as registry:
            conn = registry._store._conn
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute(
                    "INSERT INTO tags (prompt_id, tag) VALUES ('code-review', 'hax')"
                )
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("DELETE FROM prompts")
        assert dump(seeded_db) == before
