"""End-to-end CLI tests driving cli.main() the way a shell would."""

import json

import pytest

from prompt_registry.cli import main


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "registry.db"
    assert main(["--db", str(path), "init"]) == 0
    return path


@pytest.fixture
def run(db, capsys):
    def _run(*argv, expect=0):
        code = main(["--db", str(db), *argv])
        captured = capsys.readouterr()
        assert code == expect, f"{argv} -> exit {code}, stderr: {captured.err}"
        return captured.out
    return _run


@pytest.fixture
def seeded(run, tmp_path):
    body = tmp_path / "body.txt"
    body.write_text("Debug this error:\n{{ error }}\nStyle: {{ style }}\n")
    run("add", "debugger", "--name", "Debugger",
        "--description", "debugging assistant",
        "--body-file", str(body),
        "--var", "error", "--var", "style=terse",
        "--tag", "dev", "--tag", "debugging")
    return tmp_path


def test_init_is_idempotent(db, capsys):
    assert main(["--db", str(db), "init"]) == 0
    assert "already initialized" in capsys.readouterr().out


def test_commands_without_init_fail_cleanly(tmp_path, capsys):
    code = main(["--db", str(tmp_path / "missing.db"), "list"])
    assert code == 1
    assert "prompt-registry init" in capsys.readouterr().err


def test_add_and_show(run, seeded):
    out = run("show", "debugger")
    assert "id:          debugger" in out
    assert "error: required" in out
    assert "style: optional, default='terse'" in out
    assert "Debug this error:" in out


def test_add_infers_variables_from_body(run):
    run("add", "inferred", "--body", "Hello {{ who }}")
    out = run("show", "inferred")
    assert "who: required" in out


def test_add_duplicate_id_fails(run, seeded):
    run("add", "debugger", "--body", "x", expect=1)


def test_list_and_tag_filter(run, seeded):
    run("add", "other", "--body", "plain body", "--tag", "ops")
    out = run("list")
    assert "debugger" in out and "other" in out
    out = run("list", "--tag", "ops")
    assert "other" in out and "debugger" not in out


def test_search(run, seeded):
    out = run("search", "debugging")
    assert "debugger" in out
    assert "no prompts matched" in run("search", "zzz-nothing")


def test_tag_add_remove(run, seeded):
    out = run("tag", "debugger", "--add", "urgent", "--remove", "dev")
    assert "urgent" in out and "dev" not in out


def test_render_with_values_and_defaults(run, seeded):
    out = run("render", "debugger", "--var", "error=NullPointerException")
    assert "NullPointerException" in out
    assert "Style: terse" in out
    out = run("render", "debugger", "--var", "error=x", "--var", "style=verbose")
    assert "Style: verbose" in out


def test_render_missing_required_fails(run, seeded, capsys):
    run("render", "debugger", expect=1)


def test_render_vars_file(run, seeded, tmp_path):
    values = tmp_path / "values.json"
    values.write_text(json.dumps({"error": "from-file"}))
    out = run("render", "debugger", "--vars-file", str(values))
    assert "from-file" in out


def test_render_to_output_file(run, seeded, tmp_path):
    target = tmp_path / "rendered.txt"
    run("render", "debugger", "--var", "error=boom", "-o", str(target))
    assert "boom" in target.read_text()


def test_new_version_inherits_specs_and_diff(run, seeded):
    run("new-version", "debugger",
        "--body", "Debug: {{ error }} (style {{ style }}) with steps.",
        "--note", "added steps")
    out = run("show", "debugger")
    assert "version:     v2 of 2" in out
    # inherited: style keeps its default without re-declaring
    assert "style: optional, default='terse'" in out

    out = run("diff", "debugger")
    assert "v1 -> v2" in out
    assert "+Debug: {{ error }}" in out

    out = run("versions", "debugger")
    assert "v1" in out and "v2" in out and "added steps" in out


def test_identical_new_version_fails(run, seeded):
    run("new-version", "debugger",
        "--body", "Debug this error:\n{{ error }}\nStyle: {{ style }}\n",
        "--var", "error", "--var", "style=terse", expect=1)


def test_diff_explicit_versions_and_bad_range(run, seeded):
    run("diff", "debugger", expect=1)  # only one version, nothing before it
    run("new-version", "debugger", "--body", "v2 {{ error }}", "--var", "error")
    out = run("diff", "debugger", "1", "2")
    assert "v1 -> v2" in out
    assert "removed style" in out


def test_case_lifecycle_and_eval(run, seeded, tmp_path):
    run("case", "add", "debugger", "smoke",
        "--var", "error=ZeroDivisionError",
        "--check", "contains:cause",
        "--check", "not_contains:as an AI",
        "--check", "min_length:10")
    out = run("case", "list", "debugger")
    assert "smoke" in out and "3" in out
    out = run("case", "show", "debugger", "smoke")
    assert "ZeroDivisionError" in out and "contains" in out

    good = tmp_path / "good.txt"
    good.write_text("The root cause is a division by zero in line 3.")
    out = run("eval", "run", "debugger", "--output-file", str(good),
              "--rating", "4", "--note", "claude-code")
    assert "[PASS] smoke" in out
    assert "rating: 4/5" in out
    assert "1/1 checked case(s) passed" in out

    bad = tmp_path / "bad.txt"
    bad.write_text("as an AI I cannot help")
    out = run("eval", "run", "debugger", "--output-file", str(bad), expect=1)
    assert "[FAIL] smoke" in out

    out = run("eval", "history", "debugger", "--detail")
    assert "1/1 passed" in out
    assert "0/1 passed" in out
    assert "claude-code" in out


def test_case_add_validates_render(run, seeded):
    # case must supply required variables of the current version
    run("case", "add", "debugger", "incomplete", "--check", "min_length:1", expect=1)


def test_eval_without_cases_fails(run, seeded, tmp_path):
    out_file = tmp_path / "o.txt"
    out_file.write_text("output")
    run("eval", "run", "debugger", "--output-file", str(out_file), expect=1)


def test_eval_rating_only_case(run, seeded, tmp_path):
    run("case", "add", "debugger", "vibes", "--var", "error=x")
    out_file = tmp_path / "o.txt"
    out_file.write_text("output")
    out = run("eval", "run", "debugger", "--case", "vibes",
              "--output-file", str(out_file), "--rating", "5")
    assert "[N/A ] vibes" in out


def test_show_body_only_is_pipeable(run, seeded):
    out = run("show", "debugger", "--body-only")
    assert out == "Debug this error:\n{{ error }}\nStyle: {{ style }}\n"


def test_checks_file(run, seeded, tmp_path):
    checks = tmp_path / "checks.json"
    checks.write_text(json.dumps([
        {"type": "contains", "params": {"value": "Cause", "case_sensitive": False}},
    ]))
    run("case", "add", "debugger", "filed",
        "--var", "error=x", "--checks-file", str(checks))
    out_file = tmp_path / "o.txt"
    out_file.write_text("the cause is clear")
    out = run("eval", "run", "debugger", "--case", "filed",
              "--output-file", str(out_file))
    assert "[PASS] filed" in out
