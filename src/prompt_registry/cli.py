"""argparse CLI for the prompt registry.

Exit codes: 0 success, 1 domain error (RegistryError), 2 usage error.
Variable values and model outputs are never logged; --verbose logging covers
operations only.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from . import __version__, evaluator
from .diffing import diff_versions
from .errors import RegistryError, ValidationError
from .models import CheckSpec, VariableSpec
from .rendering import extract_placeholders, render
from .store import RegistryStore, resolve_db_path

logger = logging.getLogger("prompt_registry")

_INT_CHECKS = {"min_length", "max_length"}
_STR_CHECKS = {"contains": "value", "not_contains": "value", "regex": "pattern", "not_regex": "pattern"}


# -- input parsing helpers ----------------------------------------------------

def _read_body(args: argparse.Namespace) -> str:
    if args.body is not None:
        return args.body
    if args.body_file == "-":
        return sys.stdin.read()
    try:
        return Path(args.body_file).expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"cannot read body file: {exc}") from exc


def _parse_var_spec(raw: str) -> VariableSpec:
    """--var NAME (required) or --var NAME=DEFAULT (optional with default)."""
    if "=" in raw:
        name, default = raw.split("=", 1)
        return VariableSpec(name=name.strip(), required=False, default=default)
    return VariableSpec(name=raw.strip(), required=True)


def _load_var_specs(args: argparse.Namespace, body: str, previous: Sequence[VariableSpec] = ()) -> tuple[VariableSpec, ...]:
    """Resolve the variable schema for add/new-version.

    Priority: --vars-file > --var flags > inference from the template.
    Inference: reuse a previous version's spec for placeholders that survive;
    brand-new placeholders become required variables.
    """
    if args.vars_file:
        data = _load_json_file(args.vars_file, "variables file")
        if not isinstance(data, list):
            raise ValidationError("variables file must be a JSON array of specs")
        return tuple(VariableSpec.from_dict(d) for d in data)
    if args.var:
        return tuple(_parse_var_spec(v) for v in args.var)
    prev_by_name = {v.name: v for v in previous}
    return tuple(
        prev_by_name.get(name, VariableSpec(name=name, required=True))
        for name in extract_placeholders(body)
    )


def _parse_value_pairs(pairs: Sequence[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValidationError(f"expected NAME=VALUE, got {pair!r}")
        name, value = pair.split("=", 1)
        values[name.strip()] = value
    return values


def _load_json_file(path: str, what: str):
    try:
        return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(f"cannot read {what}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{what} is not valid JSON: {exc}") from exc


def _parse_check_arg(raw: str) -> CheckSpec:
    """--check 'contains:some text' | 'regex:^#' | 'max_length:500' | 'is_json'."""
    check_type, _, param = raw.partition(":")
    check_type = check_type.strip()
    if check_type in _STR_CHECKS:
        return CheckSpec(type=check_type, params={_STR_CHECKS[check_type]: param})
    if check_type in _INT_CHECKS:
        try:
            return CheckSpec(type=check_type, params={"value": int(param)})
        except ValueError as exc:
            raise ValidationError(f"check '{check_type}': expected an integer, got {param!r}") from exc
    if check_type == "is_json":
        if param:
            raise ValidationError("check 'is_json' takes no parameter")
        return CheckSpec(type="is_json")
    raise ValidationError(
        f"unknown check type '{check_type}' "
        f"(known: contains, not_contains, regex, not_regex, is_json, min_length, max_length)"
    )


def _load_checks(args: argparse.Namespace) -> tuple[CheckSpec, ...]:
    specs: list[CheckSpec] = []
    if args.checks_file:
        data = _load_json_file(args.checks_file, "checks file")
        if not isinstance(data, list):
            raise ValidationError("checks file must be a JSON array of {type, params} objects")
        specs.extend(CheckSpec.from_dict(d) for d in data)
    specs.extend(_parse_check_arg(c) for c in (args.check or []))
    return tuple(specs)


def _read_eval_output(args: argparse.Namespace) -> tuple[str, str]:
    """Return (output_text, output_source)."""
    if args.output_file:
        try:
            text = Path(args.output_file).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError(f"cannot read output file: {exc}") from exc
        return text, f"file:{args.output_file}"
    if sys.stdin.isatty():
        raise ValidationError(
            "no output to evaluate: pass --output-file or pipe the model output on stdin"
        )
    return sys.stdin.read(), "stdin"


# -- output helpers -----------------------------------------------------------

def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    lines.extend(fmt.format(*row) for row in rows)
    return "\n".join(lines)


def _describe_var(spec: VariableSpec) -> str:
    detail = "required" if spec.required else f"optional, default={spec.default!r}"
    if spec.description:
        detail += f" — {spec.description}"
    return f"{spec.name}: {detail}"


def _prompt_rows(prompts) -> list[list[str]]:
    return [
        [p.id, f"v{p.latest_version}", ",".join(p.tags) or "-", p.name]
        for p in prompts
    ]


# -- store access -------------------------------------------------------------

@contextmanager
def _open_store(args: argparse.Namespace) -> Iterator[RegistryStore]:
    with RegistryStore.open(resolve_db_path(args.db)) as store:
        yield store


# -- command handlers ---------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    path = resolve_db_path(args.db)
    if path.exists():
        print(f"registry already initialized at {path}")
        return 0
    with RegistryStore.create(path):
        pass
    print(f"initialized empty registry at {path}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    body = _read_body(args)
    variables = _load_var_specs(args, body)
    with _open_store(args) as store:
        prompt, version = store.create_prompt(
            prompt_id=args.id,
            name=args.name or args.id,
            description=args.description,
            body=body,
            variables=variables,
            tags=args.tag or [],
            note=args.note,
        )
    print(f"created prompt '{prompt.id}' v{version.version} ({version.content_hash[:12]})")
    return 0


def cmd_new_version(args: argparse.Namespace) -> int:
    body = _read_body(args)
    with _open_store(args) as store:
        previous = store.get_version(args.id)
        variables = _load_var_specs(args, body, previous=previous.variables)
        version = store.add_version(args.id, body, variables, note=args.note)
    print(f"added '{args.id}' v{version.version} ({version.content_hash[:12]})")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with _open_store(args) as store:
        prompts = store.list_prompts(tag=args.tag)
    if not prompts:
        print("no prompts found")
        return 0
    print(_table(["ID", "LATEST", "TAGS", "NAME"], _prompt_rows(prompts)))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    with _open_store(args) as store:
        prompts = store.search_prompts(args.query, tag=args.tag)
    if not prompts:
        print("no prompts matched")
        return 0
    print(_table(["ID", "LATEST", "TAGS", "NAME"], _prompt_rows(prompts)))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    with _open_store(args) as store:
        prompt = store.get_prompt(args.id)
        version = store.get_version(args.id, args.version)
        cases = store.list_cases(args.id)
    if args.body_only:
        sys.stdout.write(version.body)
        return 0
    print(f"id:          {prompt.id}")
    print(f"name:        {prompt.name}")
    if prompt.description:
        print(f"description: {prompt.description}")
    print(f"tags:        {', '.join(prompt.tags) or '-'}")
    print(f"version:     v{version.version} of {prompt.latest_version}")
    print(f"created:     {version.created_at}")
    print(f"hash:        {version.content_hash}")
    if version.note:
        print(f"note:        {version.note}")
    if version.variables:
        print("variables:")
        for spec in version.variables:
            print(f"  - {_describe_var(spec)}")
    if cases:
        print(f"eval cases:  {', '.join(c.name for c in cases)}")
    print("--- body ---")
    print(version.body)
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    if not args.add and not args.remove:
        raise ValidationError("nothing to do: pass --add and/or --remove")
    with _open_store(args) as store:
        if args.add:
            store.add_tags(args.id, args.add)
        if args.remove:
            store.remove_tags(args.id, args.remove)
        prompt = store.get_prompt(args.id)
    print(f"{prompt.id} tags: {', '.join(prompt.tags) or '-'}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    values = _parse_value_pairs(args.var or [])
    if args.vars_file:
        data = _load_json_file(args.vars_file, "values file")
        if not isinstance(data, dict):
            raise ValidationError("values file must be a JSON object of name -> value")
        values = {**data, **values}  # explicit --var wins over file
    with _open_store(args) as store:
        version = store.get_version(args.id, args.version)
    text = render(version.body, version.variables, values)
    if args.output:
        Path(args.output).expanduser().write_text(text, encoding="utf-8")
        logger.info("wrote rendered prompt to %s", args.output)
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    with _open_store(args) as store:
        latest = store.get_version(args.id)
        to_v = args.to_version if args.to_version is not None else latest.version
        from_v = args.from_version if args.from_version is not None else to_v - 1
        if from_v < 1:
            raise ValidationError(
                f"prompt '{args.id}' has no version before v{to_v} to compare against"
            )
        version_a = store.get_version(args.id, from_v)
        version_b = store.get_version(args.id, to_v)
    print(diff_versions(version_a, version_b).render_text())
    return 0


def cmd_versions(args: argparse.Namespace) -> int:
    with _open_store(args) as store:
        versions = store.list_versions(args.id)
    rows = [
        [f"v{v.version}", v.created_at, v.content_hash[:12], v.note or "-"]
        for v in versions
    ]
    print(_table(["VERSION", "CREATED", "HASH", "NOTE"], rows))
    return 0


def cmd_case_add(args: argparse.Namespace) -> int:
    variables = _parse_value_pairs(args.var or [])
    if args.vars_file:
        data = _load_json_file(args.vars_file, "values file")
        if not isinstance(data, dict):
            raise ValidationError("values file must be a JSON object of name -> value")
        variables = {**data, **variables}
    checks = _load_checks(args)
    if not checks:
        logger.warning("case '%s' has no checks; eval runs will only capture ratings", args.name)
    with _open_store(args) as store:
        # fail fast if the case variables can't render the current version
        version = store.get_version(args.id)
        render(version.body, version.variables, variables)
        case = store.add_case(args.id, args.name, variables, checks)
    print(f"added case '{case.name}' ({case.id}) with {len(case.checks)} check(s)")
    return 0


def cmd_case_list(args: argparse.Namespace) -> int:
    with _open_store(args) as store:
        cases = store.list_cases(args.id)
    if not cases:
        print("no cases found")
        return 0
    rows = [
        [c.name, c.id, str(len(c.checks)), ",".join(sorted(c.variables)) or "-"]
        for c in cases
    ]
    print(_table(["NAME", "CASE-ID", "CHECKS", "VARIABLES"], rows))
    return 0


def cmd_case_show(args: argparse.Namespace) -> int:
    with _open_store(args) as store:
        case = store.get_case(args.id, args.name)
    print(f"case:      {case.name} ({case.id})")
    print(f"prompt:    {case.prompt_id}")
    print(f"created:   {case.created_at}")
    print("variables:")
    for key in sorted(case.variables):
        print(f"  {key} = {case.variables[key]!r}")
    print("checks:")
    for spec in case.checks:
        print(f"  - {json.dumps(spec.to_dict(), ensure_ascii=False)}")
    return 0


def cmd_eval_run(args: argparse.Namespace) -> int:
    output, source = _read_eval_output(args)
    with _open_store(args) as store:
        run, evaluations = evaluator.execute_run(
            store,
            prompt_id=args.id,
            output=output,
            version=args.version,
            case_names=args.case or None,
            output_source=source,
            note=args.note,
            rating=args.rating,
            comment=args.comment,
        )
    print(f"eval run {run.id} — {run.prompt_id} v{run.prompt_version} ({source})")
    failed = 0
    for ev in evaluations:
        if ev.passed is None:
            status = "N/A "
        elif ev.passed:
            status = "PASS"
        else:
            status = "FAIL"
            failed += 1
        print(f"  [{status}] {ev.case.name}")
        for outcome in ev.outcomes:
            mark = "ok" if outcome.passed else "!!"
            print(f"      {mark} {outcome.type}: {outcome.message}")
    if args.rating is not None:
        print(f"  rating: {args.rating}/5")
    checked = [ev for ev in evaluations if ev.passed is not None]
    print(f"summary: {len(checked) - failed}/{len(checked)} checked case(s) passed")
    return 0 if failed == 0 else 1


def cmd_eval_history(args: argparse.Namespace) -> int:
    with _open_store(args) as store:
        runs = store.list_runs(args.id, limit=args.limit)
        if not runs:
            print("no eval runs recorded")
            return 0
        for run in runs:
            results = store.get_results(run.id)
            passed = sum(1 for r, _ in results if r.passed is True)
            checked = sum(1 for r, _ in results if r.passed is not None)
            ratings = [r.rating for r, _ in results if r.rating is not None]
            summary = f"{passed}/{checked} passed" if checked else "no checks"
            if ratings:
                summary += f", rating {ratings[0]}/5"
            print(f"{run.created_at}  {run.id}  v{run.prompt_version}  {summary}"
                  + (f"  ({run.note})" if run.note else ""))
            if args.detail:
                for result, case_name in results:
                    status = "N/A" if result.passed is None else ("PASS" if result.passed else "FAIL")
                    print(f"    [{status}] {case_name}")
    return 0


# -- parser wiring ------------------------------------------------------------

def _add_body_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--body", help="prompt body as an inline string")
    group.add_argument("--body-file", help="read body from a file, or '-' for stdin")
    parser.add_argument(
        "--var", action="append", metavar="NAME[=DEFAULT]",
        help="declare a variable; NAME alone is required, NAME=DEFAULT is optional "
             "(default: inferred from {{placeholders}} in the body)",
    )
    parser.add_argument("--vars-file", help="JSON array of full variable specs")
    parser.add_argument("--note", default="", help="version note")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt-registry",
        description="Local-first prompt registry and evaluator.",
    )
    parser.add_argument("--db", help="path to the registry database "
                        "(default: $PROMPT_REGISTRY_DB or ~/.prompt-registry/registry.db)")
    parser.add_argument("--verbose", action="store_true", help="log operations to stderr")
    parser.add_argument("--version", action="version", version=f"prompt-registry {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a new registry database")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add", help="create a prompt (as version 1)")
    p.add_argument("id", help="prompt id (slug)")
    p.add_argument("--name", help="human name (default: the id)")
    p.add_argument("--description", default="")
    p.add_argument("--tag", action="append", help="tag (repeatable)")
    _add_body_args(p)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("new-version", help="append a new immutable version")
    p.add_argument("id")
    _add_body_args(p)
    p.set_defaults(func=cmd_new_version)

    p = sub.add_parser("list", help="list prompts")
    p.add_argument("--tag", help="only prompts with this tag")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="substring search over id/name/description/body/tags")
    p.add_argument("query")
    p.add_argument("--tag", help="restrict to prompts with this tag")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show", help="show a prompt version")
    p.add_argument("id")
    p.add_argument("--version", type=int, help="version number (default: latest)")
    p.add_argument("--body-only", action="store_true", help="print only the raw body")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("versions", help="list a prompt's versions")
    p.add_argument("id")
    p.set_defaults(func=cmd_versions)

    p = sub.add_parser("tag", help="add or remove tags")
    p.add_argument("id")
    p.add_argument("--add", action="append", metavar="TAG")
    p.add_argument("--remove", action="append", metavar="TAG")
    p.set_defaults(func=cmd_tag)

    p = sub.add_parser("render", help="render a prompt with variable values")
    p.add_argument("id")
    p.add_argument("--version", type=int, help="version number (default: latest)")
    p.add_argument("--var", action="append", metavar="NAME=VALUE")
    p.add_argument("--vars-file", help="JSON object of name -> value")
    p.add_argument("-o", "--output", help="write to file instead of stdout")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("diff", help="compare two versions (default: previous vs latest)")
    p.add_argument("id")
    p.add_argument("from_version", nargs="?", type=int, metavar="FROM")
    p.add_argument("to_version", nargs="?", type=int, metavar="TO")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("case", help="manage eval cases")
    case_sub = p.add_subparsers(dest="case_command", required=True)

    cp = case_sub.add_parser("add", help="attach an eval case to a prompt")
    cp.add_argument("id", help="prompt id")
    cp.add_argument("name", help="case name (slug)")
    cp.add_argument("--var", action="append", metavar="NAME=VALUE",
                    help="variable value used when rendering this case")
    cp.add_argument("--vars-file", help="JSON object of name -> value")
    cp.add_argument("--check", action="append", metavar="TYPE[:PARAM]",
                    help="e.g. 'contains:foo', 'not_contains:bar', 'regex:^#', "
                         "'min_length:100', 'max_length:2000', 'is_json'")
    cp.add_argument("--checks-file", help="JSON array of {type, params} objects")
    cp.set_defaults(func=cmd_case_add)

    cp = case_sub.add_parser("list", help="list a prompt's cases")
    cp.add_argument("id")
    cp.set_defaults(func=cmd_case_list)

    cp = case_sub.add_parser("show", help="show one case in full")
    cp.add_argument("id")
    cp.add_argument("name")
    cp.set_defaults(func=cmd_case_show)

    p = sub.add_parser("eval", help="run and inspect evaluations")
    eval_sub = p.add_subparsers(dest="eval_command", required=True)

    ep = eval_sub.add_parser(
        "run",
        help="evaluate a captured model output against a prompt's cases",
        description="Render the prompt, run it in your model of choice, then feed "
                    "the output here via --output-file or stdin.",
    )
    ep.add_argument("id", help="prompt id")
    ep.add_argument("--version", type=int, help="prompt version evaluated (default: latest)")
    ep.add_argument("--case", action="append", metavar="NAME",
                    help="case to evaluate (repeatable; default: all cases)")
    ep.add_argument("--output-file", help="file containing the model output")
    ep.add_argument("--rating", type=int, help="manual quality rating 1-5")
    ep.add_argument("--comment", default="", help="manual comment")
    ep.add_argument("--note", default="", help="run note (e.g. which model produced the output)")
    ep.set_defaults(func=cmd_eval_run)

    ep = eval_sub.add_parser("history", help="show recorded eval runs")
    ep.add_argument("id")
    ep.add_argument("--limit", type=int, default=20)
    ep.add_argument("--detail", action="store_true", help="show per-case results")
    ep.set_defaults(func=cmd_eval_history)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.func(args)
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def entrypoint() -> None:
    sys.exit(main())
