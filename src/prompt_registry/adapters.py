"""Model adapter seam.

The registry core is model-agnostic and fully offline: only an adapter's
generate() ever touches a model. v1 shipped ManualAdapter (outputs captured
outside the tool). v2 adds OllamaAdapter, a zero-dependency HTTP client for a
locally running Ollama server (Gemma or any other local model Ollama serves).

Privacy rules for adapters:
- prompt text and model outputs are exchanged in-memory only
- error messages never include prompt bodies, variable values, or outputs
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .errors import AdapterError

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_URL_ENV = "OLLAMA_HOST"  # Ollama's own convention


@runtime_checkable
class ModelAdapter(Protocol):
    """Anything that can turn a rendered prompt into an output string."""

    name: str

    def generate(self, prompt_text: str) -> str:
        """Produce a model output for the given rendered prompt."""
        ...


@dataclass(frozen=True)
class ManualAdapter:
    """Wraps an output the user captured elsewhere (the v1 manual loop)."""

    output_text: str
    name: str = "manual"

    def generate(self, prompt_text: str) -> str:
        return self.output_text


def resolve_ollama_url(explicit: str | None = None) -> str:
    """--ollama-url flag > OLLAMA_HOST env > http://localhost:11434.

    Accepts 'host:port' without a scheme (Ollama's OLLAMA_HOST style).
    """
    raw = explicit or os.environ.get(OLLAMA_URL_ENV) or DEFAULT_OLLAMA_URL
    raw = raw.strip()
    if "://" not in raw:
        raw = "http://" + raw
    return raw.rstrip("/")


@dataclass(frozen=True)
class OllamaAdapter:
    """Local model execution via Ollama's /api/generate endpoint.

    temperature defaults to 0.0 so repeated evals of the same prompt version
    are as deterministic as the model allows.
    """

    model: str
    base_url: str = DEFAULT_OLLAMA_URL
    timeout_seconds: float = 120.0
    temperature: float = 0.0

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def generate(self, prompt_text: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt_text,
                "stream": False,
                "options": {"temperature": self.temperature},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise self._timeout_error() from exc
            raise AdapterError(
                f"cannot reach Ollama at {self.base_url} ({exc.reason}); "
                f"is 'ollama serve' running?"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise self._timeout_error() from exc
        except (http.client.HTTPException, OSError) as exc:
            raise AdapterError(
                f"connection to Ollama at {self.base_url} failed "
                f"({exc.__class__.__name__}: {exc}); is 'ollama serve' running?"
            ) from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterError(
                f"unexpected response from Ollama at {self.base_url}: not valid JSON"
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("response"), str):
            raise AdapterError(
                f"unexpected response from Ollama at {self.base_url}: "
                f"missing 'response' field"
            )
        return data["response"]

    def _http_error(self, exc: urllib.error.HTTPError) -> AdapterError:
        detail = self._server_error_detail(exc)
        if exc.code == 404:
            return AdapterError(
                f"model '{self.model}' not available on Ollama at {self.base_url}"
                f"{detail}; run 'ollama pull {self.model}'"
            )
        return AdapterError(
            f"Ollama at {self.base_url} returned HTTP {exc.code}{detail}"
        )

    @staticmethod
    def _server_error_detail(exc: urllib.error.HTTPError) -> str:
        """Extract Ollama's own error message, if the body carries one."""
        try:
            body = json.loads(exc.read().decode("utf-8"))
            message = body.get("error", "")
        except Exception:  # noqa: BLE001 - best-effort diagnostics only
            return ""
        if isinstance(message, str) and message:
            return f" ({message[:200]})"
        return ""

    def _timeout_error(self) -> AdapterError:
        return AdapterError(
            f"Ollama did not respond within {self.timeout_seconds:g}s "
            f"for model '{self.model}'; increase --timeout, or check that the "
            f"model is pulled and the machine isn't overloaded"
        )
