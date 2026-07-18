"""SQLite storage layer. All persistence lives here; no CLI coupling.

Guarantees:
- prompt versions are append-only and immutable (no UPDATE path exists)
- every write happens inside a transaction
- foreign keys are enforced; WAL mode for safe concurrent readers
- a schema_version stamp rejects databases from incompatible versions
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Iterable, Sequence

from .errors import (
    AlreadyExistsError,
    NotFoundError,
    StorageError,
    ValidationError,
)
from .models import (
    CheckSpec,
    EvalCase,
    EvalResult,
    EvalRun,
    Prompt,
    PromptVersion,
    VariableSpec,
    compute_content_hash,
    new_id,
    utc_now,
    validate_slug,
)
from . import checks as checks_mod
from . import rendering

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_DB_ENV = "PROMPT_REGISTRY_DB"
DEFAULT_DB_PATH = Path.home() / ".prompt-registry" / "registry.db"

_SCHEMA = """
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE prompts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE prompt_versions (
    prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    body TEXT NOT NULL,
    variables_json TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (prompt_id, version)
);
CREATE TABLE tags (
    prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (prompt_id, tag)
);
CREATE TABLE eval_cases (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    variables_json TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (prompt_id, name)
);
CREATE TABLE eval_runs (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    prompt_version INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    output_source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (prompt_id, prompt_version)
        REFERENCES prompt_versions(prompt_id, version)
);
CREATE TABLE eval_results (
    run_id TEXT NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL REFERENCES eval_cases(id) ON DELETE CASCADE,
    passed INTEGER,
    details_json TEXT NOT NULL DEFAULT '[]',
    rating INTEGER,
    comment TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, case_id)
);
CREATE INDEX idx_versions_prompt ON prompt_versions(prompt_id);
CREATE INDEX idx_cases_prompt ON eval_cases(prompt_id);
CREATE INDEX idx_runs_prompt ON eval_runs(prompt_id);
"""


def resolve_db_path(explicit: str | None) -> Path:
    """--db flag > PROMPT_REGISTRY_DB env > ~/.prompt-registry/registry.db"""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(DEFAULT_DB_ENV)
    if env:
        return Path(env).expanduser()
    return DEFAULT_DB_PATH


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


class RegistryStore:
    """All registry persistence. Use as a context manager or call close()."""

    def __init__(self, conn: sqlite3.Connection, path: Path):
        self._conn = conn
        self.path = path

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def create(cls, path: str | Path) -> "RegistryStore":
        path = Path(path).expanduser()
        if path.exists():
            raise AlreadyExistsError(f"registry already exists at {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = cls._connect(path)
        try:
            with conn:
                conn.executescript(_SCHEMA)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
        except sqlite3.Error as exc:
            conn.close()
            raise StorageError(f"failed to initialize registry at {path}: {exc}") from exc
        logger.info("initialized registry at %s", path)
        return cls(conn, path)

    @classmethod
    def open(cls, path: str | Path) -> "RegistryStore":
        path = Path(path).expanduser()
        if not path.exists():
            raise StorageError(
                f"no registry found at {path}; run 'prompt-registry init' first"
            )
        conn = cls._connect(path)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.Error as exc:
            conn.close()
            raise StorageError(f"{path} is not a prompt-registry database: {exc}") from exc
        if row is None or row["value"] != str(SCHEMA_VERSION):
            found = row["value"] if row else "none"
            conn.close()
            raise StorageError(
                f"registry at {path} has schema version {found}, "
                f"this tool requires {SCHEMA_VERSION}"
            )
        return cls(conn, path)

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(str(path))
        except sqlite3.Error as exc:
            raise StorageError(f"cannot open database at {path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error as exc:
            conn.close()
            raise StorageError(f"{path} is not a prompt-registry database: {exc}") from exc
        return conn

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RegistryStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- prompts -------------------------------------------------------------

    def create_prompt(
        self,
        prompt_id: str,
        name: str,
        description: str,
        body: str,
        variables: Sequence[VariableSpec],
        tags: Iterable[str] = (),
        note: str = "",
    ) -> tuple[Prompt, PromptVersion]:
        validate_slug(prompt_id, "prompt id")
        if not name.strip():
            raise ValidationError("prompt name must not be empty")
        if not body.strip():
            raise ValidationError("prompt body must not be empty")
        rendering.validate_template(body, variables)
        normalized_tags = sorted({validate_slug(t.lower(), "tag") for t in tags})
        now = utc_now()
        version = PromptVersion(
            prompt_id=prompt_id,
            version=1,
            body=body,
            variables=tuple(variables),
            note=note,
            content_hash=compute_content_hash(body, variables),
            created_at=now,
        )
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO prompts (id, name, description, created_at) VALUES (?, ?, ?, ?)",
                    (prompt_id, name, description, now),
                )
                self._insert_version(version)
                self._conn.executemany(
                    "INSERT INTO tags (prompt_id, tag) VALUES (?, ?)",
                    [(prompt_id, t) for t in normalized_tags],
                )
        except sqlite3.IntegrityError as exc:
            raise AlreadyExistsError(f"prompt '{prompt_id}' already exists") from exc
        logger.info("created prompt '%s' (v1)", prompt_id)
        return self.get_prompt(prompt_id), version

    def get_prompt(self, prompt_id: str) -> Prompt:
        row = self._conn.execute(
            "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"prompt '{prompt_id}' not found")
        return self._build_prompt(row)

    def _build_prompt(self, row: sqlite3.Row) -> Prompt:
        tags = tuple(
            r["tag"]
            for r in self._conn.execute(
                "SELECT tag FROM tags WHERE prompt_id = ? ORDER BY tag", (row["id"],)
            )
        )
        latest = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM prompt_versions WHERE prompt_id = ?",
            (row["id"],),
        ).fetchone()["v"]
        return Prompt(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            tags=tags,
            latest_version=latest,
        )

    def list_prompts(self, tag: str | None = None) -> list[Prompt]:
        if tag:
            rows = self._conn.execute(
                "SELECT p.* FROM prompts p JOIN tags t ON t.prompt_id = p.id "
                "WHERE t.tag = ? ORDER BY p.id",
                (tag.lower(),),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM prompts ORDER BY id").fetchall()
        return [self._build_prompt(r) for r in rows]

    def search_prompts(self, query: str, tag: str | None = None) -> list[Prompt]:
        """Substring search over id, name, description, latest body, and tags."""
        pattern = _like_pattern(query)
        sql = r"""
            SELECT DISTINCT p.* FROM prompts p
            JOIN prompt_versions v ON v.prompt_id = p.id
                AND v.version = (SELECT MAX(version) FROM prompt_versions WHERE prompt_id = p.id)
            LEFT JOIN tags t ON t.prompt_id = p.id
            WHERE (p.id LIKE :pat ESCAPE '\'
                OR p.name LIKE :pat ESCAPE '\'
                OR p.description LIKE :pat ESCAPE '\'
                OR v.body LIKE :pat ESCAPE '\'
                OR t.tag LIKE :pat ESCAPE '\')
        """
        params: dict[str, str] = {"pat": pattern}
        if tag:
            sql += " AND p.id IN (SELECT prompt_id FROM tags WHERE tag = :tag)"
            params["tag"] = tag.lower()
        sql += " ORDER BY p.id"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._build_prompt(r) for r in rows]

    # -- versions ------------------------------------------------------------

    def _insert_version(self, version: PromptVersion) -> None:
        self._conn.execute(
            "INSERT INTO prompt_versions "
            "(prompt_id, version, body, variables_json, note, content_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                version.prompt_id,
                version.version,
                version.body,
                version.variables_json(),
                version.note,
                version.content_hash,
                version.created_at,
            ),
        )

    def add_version(
        self,
        prompt_id: str,
        body: str,
        variables: Sequence[VariableSpec],
        note: str = "",
    ) -> PromptVersion:
        if not body.strip():
            raise ValidationError("prompt body must not be empty")
        rendering.validate_template(body, variables)
        latest = self.get_version(prompt_id)  # raises NotFoundError if no prompt
        content_hash = compute_content_hash(body, variables)
        if content_hash == latest.content_hash:
            raise ValidationError(
                f"new version is identical to v{latest.version}; nothing to add"
            )
        version = PromptVersion(
            prompt_id=prompt_id,
            version=latest.version + 1,
            body=body,
            variables=tuple(variables),
            note=note,
            content_hash=content_hash,
            created_at=utc_now(),
        )
        with self._conn:
            self._insert_version(version)
        logger.info("added version v%d to prompt '%s'", version.version, prompt_id)
        return version

    def get_version(self, prompt_id: str, version: int | None = None) -> PromptVersion:
        """Fetch a specific version, or the latest when version is None."""
        self.get_prompt(prompt_id)  # ensure a clear error for unknown prompts
        if version is None:
            row = self._conn.execute(
                "SELECT * FROM prompt_versions WHERE prompt_id = ? "
                "ORDER BY version DESC LIMIT 1",
                (prompt_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM prompt_versions WHERE prompt_id = ? AND version = ?",
                (prompt_id, version),
            ).fetchone()
        if row is None:
            label = "any version" if version is None else f"version {version}"
            raise NotFoundError(f"prompt '{prompt_id}' has no {label}")
        return self._version_from_row(row)

    def list_versions(self, prompt_id: str) -> list[PromptVersion]:
        self.get_prompt(prompt_id)
        rows = self._conn.execute(
            "SELECT * FROM prompt_versions WHERE prompt_id = ? ORDER BY version",
            (prompt_id,),
        ).fetchall()
        return [self._version_from_row(r) for r in rows]

    @staticmethod
    def _version_from_row(row: sqlite3.Row) -> PromptVersion:
        return PromptVersion(
            prompt_id=row["prompt_id"],
            version=row["version"],
            body=row["body"],
            variables=PromptVersion.parse_variables(row["variables_json"]),
            note=row["note"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
        )

    # -- tags ----------------------------------------------------------------

    def add_tags(self, prompt_id: str, tags: Iterable[str]) -> Prompt:
        self.get_prompt(prompt_id)
        normalized = sorted({validate_slug(t.lower(), "tag") for t in tags})
        with self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO tags (prompt_id, tag) VALUES (?, ?)",
                [(prompt_id, t) for t in normalized],
            )
        return self.get_prompt(prompt_id)

    def remove_tags(self, prompt_id: str, tags: Iterable[str]) -> Prompt:
        self.get_prompt(prompt_id)
        with self._conn:
            self._conn.executemany(
                "DELETE FROM tags WHERE prompt_id = ? AND tag = ?",
                [(prompt_id, t.lower()) for t in tags],
            )
        return self.get_prompt(prompt_id)

    # -- eval cases ----------------------------------------------------------

    def add_case(
        self,
        prompt_id: str,
        name: str,
        variables: dict[str, str],
        checks: Sequence[CheckSpec],
    ) -> EvalCase:
        validate_slug(name, "case name")
        self.get_prompt(prompt_id)
        for spec in checks:
            checks_mod.validate_check(spec)
        for key, value in variables.items():
            if not isinstance(value, str):
                raise ValidationError(f"case variable '{key}': value must be a string")
        case = EvalCase(
            id=new_id(),
            prompt_id=prompt_id,
            name=name,
            variables=dict(variables),
            checks=tuple(checks),
            created_at=utc_now(),
        )
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO eval_cases "
                    "(id, prompt_id, name, variables_json, checks_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        case.id,
                        case.prompt_id,
                        case.name,
                        case.variables_json(),
                        case.checks_json(),
                        case.created_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AlreadyExistsError(
                f"case '{name}' already exists for prompt '{prompt_id}'"
            ) from exc
        logger.info("added case '%s' to prompt '%s'", name, prompt_id)
        return case

    def list_cases(self, prompt_id: str) -> list[EvalCase]:
        self.get_prompt(prompt_id)
        rows = self._conn.execute(
            "SELECT * FROM eval_cases WHERE prompt_id = ? ORDER BY name", (prompt_id,)
        ).fetchall()
        return [self._case_from_row(r) for r in rows]

    def get_case(self, prompt_id: str, name: str) -> EvalCase:
        row = self._conn.execute(
            "SELECT * FROM eval_cases WHERE prompt_id = ? AND name = ?",
            (prompt_id, name),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"case '{name}' not found for prompt '{prompt_id}'")
        return self._case_from_row(row)

    @staticmethod
    def _case_from_row(row: sqlite3.Row) -> EvalCase:
        return EvalCase(
            id=row["id"],
            prompt_id=row["prompt_id"],
            name=row["name"],
            variables=json.loads(row["variables_json"]),
            checks=tuple(
                CheckSpec.from_dict(d) for d in json.loads(row["checks_json"])
            ),
            created_at=row["created_at"],
        )

    # -- eval runs & results -------------------------------------------------

    def record_run(self, run: EvalRun, results: Sequence[EvalResult]) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO eval_runs "
                "(id, prompt_id, prompt_version, note, output_source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run.id,
                    run.prompt_id,
                    run.prompt_version,
                    run.note,
                    run.output_source,
                    run.created_at,
                ),
            )
            self._conn.executemany(
                "INSERT INTO eval_results "
                "(run_id, case_id, passed, details_json, rating, comment) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        r.run_id,
                        r.case_id,
                        None if r.passed is None else int(r.passed),
                        r.details_json(),
                        r.rating,
                        r.comment,
                    )
                    for r in results
                ],
            )
        logger.info(
            "recorded eval run %s for '%s' v%d (%d case(s))",
            run.id, run.prompt_id, run.prompt_version, len(results),
        )

    def list_runs(self, prompt_id: str, limit: int = 20) -> list[EvalRun]:
        self.get_prompt(prompt_id)
        rows = self._conn.execute(
            "SELECT * FROM eval_runs WHERE prompt_id = ? "
            "ORDER BY created_at DESC, id LIMIT ?",
            (prompt_id, limit),
        ).fetchall()
        return [
            EvalRun(
                id=r["id"],
                prompt_id=r["prompt_id"],
                prompt_version=r["prompt_version"],
                note=r["note"],
                output_source=r["output_source"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_results(self, run_id: str) -> list[tuple[EvalResult, str]]:
        """Results for a run, each paired with its case name."""
        rows = self._conn.execute(
            "SELECT r.*, c.name AS case_name FROM eval_results r "
            "JOIN eval_cases c ON c.id = r.case_id WHERE r.run_id = ? "
            "ORDER BY c.name",
            (run_id,),
        ).fetchall()
        return [
            (
                EvalResult(
                    run_id=r["run_id"],
                    case_id=r["case_id"],
                    passed=None if r["passed"] is None else bool(r["passed"]),
                    details=tuple(json.loads(r["details_json"])),
                    rating=r["rating"],
                    comment=r["comment"],
                ),
                r["case_name"],
            )
            for r in rows
        ]
