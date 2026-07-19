"""MCP server tests: missing-extra behavior (no SDK needed) and a genuine
stdio protocol round-trip (skipped when the optional SDK isn't installed)."""

import asyncio
import importlib.util
import json
import sys

import pytest

from prompt_registry.mcp import entry
from prompt_registry.models import VariableSpec
from prompt_registry.store import RegistryStore

APPROVED_TOOLS = {
    "search_prompts",
    "get_prompt",
    "render_prompt",
    "list_prompt_versions",
}


@pytest.fixture
def seeded_db(tmp_path):
    path = tmp_path / "registry.db"
    with RegistryStore.create(path) as store:
        store.create_prompt(
            "debugger", "Debugger", "debugging assistant",
            "Debug: {{ error }}", (VariableSpec(name="error"),), tags=["dev"],
        )
    return path


class TestMissingExtra:
    def test_clear_message_and_exit_3(self, monkeypatch, capsys, tmp_path):
        real_find_spec = importlib.util.find_spec
        monkeypatch.setattr(
            importlib.util, "find_spec",
            lambda name, *a, **kw: None if name == "mcp" else real_find_spec(name, *a, **kw),
        )
        code = entry.main(["--db", str(tmp_path / "r.db")])
        captured = capsys.readouterr()
        assert code == 3
        assert "pip install 'prompt-registry[mcp]'" in captured.err
        assert captured.out == ""  # stdout stays clean even on failure

    def test_startup_diagnostics_hide_db_path_by_default(self, capsys, tmp_path,
                                                         monkeypatch):
        pytest.importorskip("mcp")
        # stop before actually serving: make run() a no-op
        from prompt_registry.mcp import server as server_mod

        class FakeApp:
            def run(self, transport):
                assert transport == "stdio"

        monkeypatch.setattr(server_mod, "create_server", lambda db: FakeApp())
        secret_dir = tmp_path / "hakan-private"
        secret_dir.mkdir()
        db = secret_dir / "registry.db"

        assert entry.main(["--db", str(db)]) == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "database=configured" in captured.err
        assert str(db) not in captured.err  # path hidden without --debug
        assert "registry_unavailable" in captured.err  # missing-db warning

        assert entry.main(["--db", str(db), "--debug"]) == 0
        assert str(db) in capsys.readouterr().err  # opt-in path disclosure


def _call(session_coro):
    return asyncio.run(session_coro)


@pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason="optional MCP SDK not installed",
)
class TestStdioProtocol:
    def _run_session(self, db_path, actions, tmp_path_factory=None):
        """Spawn the real server subprocess and drive it over stdio."""
        import os

        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        async def session_flow():
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "prompt_registry.mcp", "--db", str(db_path)],
            )
            # pytest's captured stderr has no fileno(); give the server's
            # stderr a real sink so the subprocess can be spawned
            with open(os.devnull, "w", encoding="utf-8") as errlog:
                async with stdio_client(params, errlog=errlog) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await actions(session)

        return _call(session_flow())

    @staticmethod
    def _payload(result):
        assert not result.isError
        return json.loads(result.content[0].text)

    def test_tools_list_is_exactly_the_approved_surface(self, seeded_db):
        async def actions(session):
            listing = await session.list_tools()
            return {t.name for t in listing.tools}

        assert self._run_session(seeded_db, actions) == APPROVED_TOOLS

    def test_end_to_end_tool_calls(self, seeded_db):
        async def actions(session):
            return {
                "search": await session.call_tool(
                    "search_prompts", {"query": "debug"}
                ),
                "get": await session.call_tool(
                    "get_prompt", {"prompt": "debugger"}
                ),
                "render": await session.call_tool(
                    "render_prompt",
                    {"prompt": "debugger", "variables": {"error": "KeyError"}},
                ),
                "versions": await session.call_tool(
                    "list_prompt_versions", {"prompt": "debugger"}
                ),
                "render_fail": await session.call_tool(
                    "render_prompt", {"prompt": "debugger", "variables": {}}
                ),
            }

        results = self._run_session(seeded_db, actions)

        search = self._payload(results["search"])
        assert search["data"]["results"][0]["id"] == "debugger"

        got = self._payload(results["get"])
        assert got["data"]["selected_version"]["number"] == 1
        assert got["data"]["selected_version"]["body"] == "Debug: {{ error }}"

        rendered = self._payload(results["render"])
        assert rendered["data"]["rendered"] == "Debug: KeyError"
        assert rendered["data"]["version_number"] == 1

        versions = self._payload(results["versions"])
        assert [v["number"] for v in versions["data"]["versions"]] == [1]

        failed = self._payload(results["render_fail"])
        assert failed["ok"] is False
        assert failed["error"]["code"] == "render_error"

    def test_missing_db_yields_structured_error_not_crash(self, tmp_path):
        async def actions(session):
            return await session.call_tool("search_prompts", {"query": ""})

        result = self._run_session(tmp_path / "missing.db", actions)
        payload = self._payload(result)
        assert payload["error"]["code"] == "registry_unavailable"
