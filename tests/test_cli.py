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


class TestAdapterMode:
    @pytest.fixture
    def cased(self, run, seeded):
        run("case", "add", "debugger", "smoke",
            "--var", "error=ZeroDivisionError",
            "--check", "contains:cause", "--check", "min_length:5")

    def test_model_and_output_file_mutually_exclusive(self, run, cased, tmp_path):
        out_file = tmp_path / "o.txt"
        out_file.write_text("x")
        run("eval", "run", "debugger", "--model", "gemma3",
            "--output-file", str(out_file), expect=1)

    def test_adapter_flags_require_model(self, run, cased, capsys):
        run("eval", "run", "debugger", "--ollama-url", "http://x:1", expect=1)
        run("eval", "run", "debugger", "--show-output", expect=1)

    def test_one_command_loop_against_stub(self, run, cased, ollama_stub):
        ollama_stub.respond_with("The root cause is division by zero.")
        out = run("eval", "run", "debugger", "--model", "gemma3",
                  "--ollama-url", ollama_stub.url, "--note", "stub")
        assert "[PASS] smoke" in out
        assert "(ollama:gemma3)" in out
        assert "1/1 checked case(s) passed" in out
        # the rendered prompt (with case variables) reached the "model"
        assert "ZeroDivisionError" in ollama_stub.requests[0]["prompt"]
        # run was recorded with the adapter as output source
        history = run("eval", "history", "debugger")
        assert "1/1 passed" in history and "stub" in history

    def test_failing_checks_exit_1(self, run, cased, ollama_stub):
        ollama_stub.respond_with("I have no idea.")
        out = run("eval", "run", "debugger", "--model", "gemma3",
                  "--ollama-url", ollama_stub.url, expect=1)
        assert "[FAIL] smoke" in out

    def test_show_output_prints_generated_text(self, run, cased, ollama_stub):
        ollama_stub.respond_with("The root cause is division by zero.")
        out = run("eval", "run", "debugger", "--model", "gemma3",
                  "--ollama-url", ollama_stub.url, "--show-output")
        assert "| The root cause is division by zero." in out

    def test_output_hidden_by_default(self, run, cased, ollama_stub):
        ollama_stub.respond_with("The root cause is division by zero.")
        out = run("eval", "run", "debugger", "--model", "gemma3",
                  "--ollama-url", ollama_stub.url)
        assert "division by zero" not in out

    def test_unreachable_server_fails_cleanly(self, db, cased, capsys):
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            dead_port = sock.getsockname()[1]
        code = main(["--db", str(db), "eval", "run", "debugger",
                     "--model", "gemma3", "--timeout", "2",
                     "--ollama-url", f"http://127.0.0.1:{dead_port}"])
        captured = capsys.readouterr()
        assert code == 1
        assert "ollama serve" in captured.err
        # atomic: no run recorded
        code = main(["--db", str(db), "eval", "history", "debugger"])
        assert "no eval runs recorded" in capsys.readouterr().out

    def test_missing_model_fails_cleanly(self, db, cased, ollama_stub, capsys):
        ollama_stub.status = 404
        ollama_stub.body = json.dumps({"error": "model not found"}).encode()
        code = main(["--db", str(db), "eval", "run", "debugger",
                     "--model", "gemma9", "--ollama-url", ollama_stub.url])
        captured = capsys.readouterr()
        assert code == 1
        assert "ollama pull gemma9" in captured.err

    def test_manual_mode_unchanged(self, run, cased, tmp_path):
        # the v1 flow still works exactly as before
        good = tmp_path / "good.txt"
        good.write_text("The root cause is a division by zero.")
        out = run("eval", "run", "debugger", "--output-file", str(good))
        assert "[PASS] smoke" in out
