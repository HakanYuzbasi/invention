"""Tests for the SDK-free MCP tool layer (no MCP SDK required)."""

import logging
import sqlite3

import pytest

from prompt_registry.mcp import tools
from prompt_registry.models import VariableSpec
from prompt_registry.store import RegistryStore


def dump(db_path) -> str:
    with sqlite3.connect(str(db_path)) as conn:
        return "\n".join(conn.iterdump())


@pytest.fixture
def seeded_db(tmp_path):
    path = tmp_path / "registry.db"
    with RegistryStore.create(path) as store:
        store.create_prompt(
            "debugger", "Debugger", "debugging assistant",
            "Debug this error:\n{{ error }}\nStyle: {{ style }}",
            (
                VariableSpec(name="error"),
                VariableSpec(name="style", required=False, default="terse"),
            ),
            tags=["dev", "debugging"],
        )
        store.add_version(
            "debugger", "Debug carefully: {{ error }}",
            (VariableSpec(name="error"),), note="v2 simplification",
        )
        store.create_prompt("plain", "Plain", "no variables", "Just do it.", ())
    return path


class TestSearchPrompts:
    def test_search_shape(self, seeded_db):
        result = tools.search_prompts(seeded_db, query="debugging")
        assert result["ok"] is True
        (hit,) = result["data"]["results"]
        assert hit["id"] == "debugger"
        assert hit["name"] == "Debugger"
        assert hit["tags"] == ["debugging", "dev"]
        assert hit["latest_version"] == 2
        assert hit["preview"].startswith("Debug carefully:")

    def test_empty_query_lists_all(self, seeded_db):
        result = tools.search_prompts(seeded_db, query="")
        assert [r["id"] for r in result["data"]["results"]] == ["debugger", "plain"]

    def test_tag_filter_and_limit(self, seeded_db):
        result = tools.search_prompts(seeded_db, query="", tag="dev")
        assert [r["id"] for r in result["data"]["results"]] == ["debugger"]
        result = tools.search_prompts(seeded_db, query="", limit=1)
        assert len(result["data"]["results"]) == 1

    def test_bad_limit_type(self, seeded_db):
        result = tools.search_prompts(seeded_db, query="", limit="ten")
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_input"


class TestGetPrompt:
    def test_latest_by_default(self, seeded_db):
        result = tools.get_prompt(seeded_db, "debugger")
        data = result["data"]
        assert data["latest_version"] == 2
        assert data["selected_version"]["number"] == 2
        assert data["selected_version"]["body"] == "Debug carefully: {{ error }}"
        assert data["selected_version"]["note"] == "v2 simplification"
        assert len(data["selected_version"]["content_hash"]) == 64
        assert data["selected_version"]["variables"] == [
            {"name": "error", "description": "", "required": True, "default": None}
        ]

    def test_explicit_historical_version(self, seeded_db):
        result = tools.get_prompt(seeded_db, "debugger", version=1)
        data = result["data"]
        assert data["latest_version"] == 2
        assert data["selected_version"]["number"] == 1
        assert "Style: {{ style }}" in data["selected_version"]["body"]

    def test_lookup_by_name(self, seeded_db):
        result = tools.get_prompt(seeded_db, "Debugger")
        assert result["data"]["id"] == "debugger"

    def test_unknown_prompt(self, seeded_db):
        result = tools.get_prompt(seeded_db, "ghost")
        assert result["ok"] is False
        assert result["error"]["code"] == "not_found"

    def test_unknown_version(self, seeded_db):
        result = tools.get_prompt(seeded_db, "debugger", version=99)
        assert result["error"]["code"] == "not_found"

    def test_bad_version_arg(self, seeded_db):
        for bad in (0, -1, "one", True):
            result = tools.get_prompt(seeded_db, "debugger", version=bad)
            assert result["error"]["code"] == "invalid_input"


class TestRenderPrompt:
    def test_render_with_defaults(self, seeded_db):
        result = tools.render_prompt(
            seeded_db, "debugger", variables={"error": "KeyError"}, version=1
        )
        data = result["data"]
        assert data["version_number"] == 1
        assert "KeyError" in data["rendered"]
        assert "Style: terse" in data["rendered"]

    def test_render_latest(self, seeded_db):
        result = tools.render_prompt(seeded_db, "debugger", {"error": "boom"})
        assert result["data"]["version_number"] == 2
        assert result["data"]["rendered"] == "Debug carefully: boom"

    def test_render_no_variables_prompt(self, seeded_db):
        result = tools.render_prompt(seeded_db, "plain")
        assert result["data"]["rendered"] == "Just do it."

    def test_missing_required_variable(self, seeded_db):
        result = tools.render_prompt(seeded_db, "debugger", variables={})
        assert result["ok"] is False
        assert result["error"]["code"] == "render_error"
        assert "error" in result["error"]["message"]  # names the variable

    def test_unknown_variable(self, seeded_db):
        result = tools.render_prompt(
            seeded_db, "debugger", {"error": "x", "bogus": "y"}
        )
        assert result["error"]["code"] == "render_error"
        assert "bogus" in result["error"]["message"]

    def test_non_string_value_names_key_never_value(self, seeded_db):
        secret_number = 424242424242
        result = tools.render_prompt(
            seeded_db, "debugger", {"error": secret_number}
        )
        assert result["error"]["code"] == "invalid_input"
        assert "error" in result["error"]["message"]
        assert str(secret_number) not in result["error"]["message"]

    def test_non_mapping_variables(self, seeded_db):
        result = tools.render_prompt(seeded_db, "debugger", variables=["x"])
        assert result["error"]["code"] == "invalid_input"


class TestListPromptVersions:
    def test_shape(self, seeded_db):
        result = tools.list_prompt_versions(seeded_db, "debugger")
        versions = result["data"]["versions"]
        assert [v["number"] for v in versions] == [1, 2]
        assert versions[1]["note"] == "v2 simplification"
        assert all(len(v["content_hash"]) == 64 for v in versions)


class TestRegistryErrors:
    def test_missing_db_is_registry_unavailable(self, tmp_path):
        missing = tmp_path / "nope.db"
        for call in (
            lambda: tools.search_prompts(missing, query="x"),
            lambda: tools.get_prompt(missing, "p"),
            lambda: tools.render_prompt(missing, "p", {}),
            lambda: tools.list_prompt_versions(missing, "p"),
        ):
            result = call()
            assert result["ok"] is False
            assert result["error"]["code"] == "registry_unavailable"
            assert "prompt-registry init" in result["error"]["message"]
            assert str(missing) not in result["error"]["message"]

    def test_invalid_file_is_registry_invalid(self, tmp_path):
        junk = tmp_path / "junk.db"
        junk.write_text("this is not sqlite")
        result = tools.get_prompt(junk, "p")
        assert result["error"]["code"] == "registry_invalid"
        assert str(junk) not in result["error"]["message"]

    def test_envelopes_never_contain_db_path(self, seeded_db):
        results = [
            tools.search_prompts(seeded_db, query=""),
            tools.get_prompt(seeded_db, "ghost"),
            tools.render_prompt(seeded_db, "debugger", {}),
            tools.list_prompt_versions(seeded_db, "debugger"),
        ]
        for result in results:
            assert str(seeded_db) not in repr(result)


class TestPrivacyAndNoMutation:
    SENTINEL = "TOP-SECRET-VALUE-8f3a1"

    def test_variables_and_output_never_logged_or_persisted(
        self, seeded_db, caplog, capsys
    ):
        with caplog.at_level(logging.DEBUG):
            result = tools.render_prompt(
                seeded_db, "debugger", {"error": self.SENTINEL}
            )
        assert self.SENTINEL in result["data"]["rendered"]  # returned to caller
        assert self.SENTINEL not in caplog.text
        captured = capsys.readouterr()
        assert self.SENTINEL not in captured.out
        assert self.SENTINEL not in captured.err
        # never written to the DB or any journal/WAL sibling file
        for path in seeded_db.parent.glob(seeded_db.name + "*"):
            assert self.SENTINEL.encode() not in path.read_bytes()

    def test_no_mutation_across_every_tool_call(self, seeded_db):
        calls = [
            lambda: tools.search_prompts(seeded_db, query="debug"),
            lambda: tools.get_prompt(seeded_db, "debugger"),
            lambda: tools.get_prompt(seeded_db, "debugger", version=1),
            lambda: tools.render_prompt(seeded_db, "debugger", {"error": "x"}),
            lambda: tools.render_prompt(seeded_db, "debugger", {}),  # error path
            lambda: tools.list_prompt_versions(seeded_db, "debugger"),
            lambda: tools.get_prompt(seeded_db, "ghost"),  # error path
        ]
        before = dump(seeded_db)
        for call in calls:
            call()
            assert dump(seeded_db) == before
