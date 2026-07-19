"""Source-level proof that the MCP package and the read-only facade contain
no mutation path: no store mutation calls, no eval/model execution, no write
SQL. This test fails the build if anyone wires a write into the access layer."""

import re
from pathlib import Path

import prompt_registry.mcp
import prompt_registry.readonly
from prompt_registry.readonly import ReadOnlyRegistry

MCP_PACKAGE_DIR = Path(prompt_registry.mcp.__file__).parent
READONLY_MODULE = Path(prompt_registry.readonly.__file__)

FORBIDDEN_IDENTIFIERS = [
    "create_prompt",
    "add_version",
    "add_tags",
    "remove_tags",
    "add_case",
    "record_run",
    "execute_run",
    "execute_adapter_run",
    "OllamaAdapter",
    "ManualAdapter",
    "executescript",
    "executemany",
    "RegistryStore.create",
]

# uppercase SQL verbs as whole words, the way any embedded SQL would spell them
FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|REPLACE|CREATE TABLE|CREATE INDEX)\b"
)


def _scanned_sources() -> list[Path]:
    files = sorted(MCP_PACKAGE_DIR.glob("*.py")) + [READONLY_MODULE]
    assert len(files) >= 6, "expected the whole MCP package plus readonly.py"
    return files


def test_no_mutation_identifiers_in_access_layer():
    for path in _scanned_sources():
        source = path.read_text(encoding="utf-8")
        for identifier in FORBIDDEN_IDENTIFIERS:
            assert identifier not in source, (
                f"{path.name} references forbidden mutation/execution "
                f"identifier '{identifier}'"
            )


def test_no_write_sql_in_access_layer():
    for path in _scanned_sources():
        source = path.read_text(encoding="utf-8")
        match = FORBIDDEN_SQL.search(source)
        assert match is None, (
            f"{path.name} contains write-oriented SQL verb '{match.group(0)}'"
        )


def test_facade_exposes_no_mutation_attributes():
    public = [name for name in dir(ReadOnlyRegistry) if not name.startswith("_")]
    assert sorted(public) == [
        "close", "get_prompt", "get_version", "list_versions", "open",
        "resolve", "search",
    ]


def test_mcp_package_never_imports_mutation_modules():
    for path in MCP_PACKAGE_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for module in ("evaluator", "adapters", "checks", "diffing"):
            assert not re.search(rf"\bimport\b.*\b{module}\b", source), (
                f"{path.name} imports '{module}', which is outside the "
                f"read-only boundary"
            )
