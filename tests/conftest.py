import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from prompt_registry.models import VariableSpec
from prompt_registry.store import RegistryStore


@pytest.fixture
def store(tmp_path):
    with RegistryStore.create(tmp_path / "registry.db") as s:
        yield s


@dataclass
class OllamaStub:
    """Configurable fake Ollama server for adapter tests."""

    url: str = ""
    status: int = 200
    body: bytes = b""
    delay_seconds: float = 0.0
    requests: list = field(default_factory=list)

    def respond_with(self, response_text: str) -> None:
        self.status = 200
        self.body = json.dumps({"response": response_text}).encode()


@pytest.fixture
def ollama_stub():
    stub = OllamaStub()
    stub.respond_with("stub output")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server API
            length = int(self.headers.get("Content-Length", 0))
            stub.requests.append(json.loads(self.rfile.read(length)))
            if stub.delay_seconds:
                time.sleep(stub.delay_seconds)
            self.send_response(stub.status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(stub.body)

        def log_message(self, *args):  # keep test output clean
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    stub.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield stub
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def sample_prompt(store):
    """A prompt with one required and one optional variable, version 1."""
    body = "Review {{ code }} with tone {{ tone }}."
    variables = (
        VariableSpec(name="code", required=True),
        VariableSpec(name="tone", required=False, default="strict"),
    )
    prompt, version = store.create_prompt(
        prompt_id="code-review",
        name="Code Review",
        description="Reviews code snippets",
        body=body,
        variables=variables,
        tags=["dev", "review"],
    )
    return prompt, version
