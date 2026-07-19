import json
import socket

import pytest

from prompt_registry.adapters import (
    DEFAULT_OLLAMA_URL,
    ManualAdapter,
    ModelAdapter,
    OllamaAdapter,
    resolve_ollama_url,
)
from prompt_registry.errors import AdapterError


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestResolveOllamaUrl:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        assert resolve_ollama_url() == DEFAULT_OLLAMA_URL

    def test_explicit_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://env:1")
        assert resolve_ollama_url("http://flag:2") == "http://flag:2"

    def test_env_used(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://envhost:1234")
        assert resolve_ollama_url() == "http://envhost:1234"

    def test_scheme_added_and_slash_stripped(self):
        assert resolve_ollama_url("myhost:11434/") == "http://myhost:11434"


class TestProtocol:
    def test_adapters_satisfy_protocol(self):
        assert isinstance(ManualAdapter(output_text="x"), ModelAdapter)
        assert isinstance(OllamaAdapter(model="gemma3"), ModelAdapter)

    def test_ollama_adapter_name(self):
        assert OllamaAdapter(model="gemma3").name == "ollama:gemma3"


class TestOllamaGenerate:
    def test_success_and_request_shape(self, ollama_stub):
        ollama_stub.respond_with("model says hi")
        adapter = OllamaAdapter(model="gemma3", base_url=ollama_stub.url,
                                temperature=0.3)
        assert adapter.generate("rendered prompt") == "model says hi"

        request = ollama_stub.requests[0]
        assert request["model"] == "gemma3"
        assert request["prompt"] == "rendered prompt"
        assert request["stream"] is False
        assert request["options"] == {"temperature": 0.3}

    def test_temperature_defaults_to_zero(self, ollama_stub):
        OllamaAdapter(model="m", base_url=ollama_stub.url).generate("p")
        assert ollama_stub.requests[0]["options"] == {"temperature": 0.0}

    def test_model_missing_404(self, ollama_stub):
        ollama_stub.status = 404
        ollama_stub.body = json.dumps({"error": "model 'gemma9' not found"}).encode()
        adapter = OllamaAdapter(model="gemma9", base_url=ollama_stub.url)
        with pytest.raises(AdapterError, match="ollama pull gemma9"):
            adapter.generate("p")

    def test_server_error_includes_status(self, ollama_stub):
        ollama_stub.status = 500
        ollama_stub.body = json.dumps({"error": "boom"}).encode()
        adapter = OllamaAdapter(model="m", base_url=ollama_stub.url)
        with pytest.raises(AdapterError, match=r"HTTP 500 \(boom\)"):
            adapter.generate("p")

    def test_malformed_json_response(self, ollama_stub):
        ollama_stub.body = b"<html>not json</html>"
        adapter = OllamaAdapter(model="m", base_url=ollama_stub.url)
        with pytest.raises(AdapterError, match="not valid JSON"):
            adapter.generate("p")

    def test_missing_response_field(self, ollama_stub):
        ollama_stub.body = json.dumps({"done": True}).encode()
        adapter = OllamaAdapter(model="m", base_url=ollama_stub.url)
        with pytest.raises(AdapterError, match="missing 'response' field"):
            adapter.generate("p")

    def test_server_unreachable(self):
        adapter = OllamaAdapter(
            model="m", base_url=f"http://127.0.0.1:{_free_port()}",
            timeout_seconds=2,
        )
        with pytest.raises(AdapterError, match="is 'ollama serve' running"):
            adapter.generate("p")

    def test_timeout(self, ollama_stub):
        ollama_stub.delay_seconds = 1.5
        adapter = OllamaAdapter(model="m", base_url=ollama_stub.url,
                                timeout_seconds=0.3)
        with pytest.raises(AdapterError, match="did not respond within 0.3s"):
            adapter.generate("p")

    def test_error_messages_never_contain_prompt_text(self, ollama_stub):
        secret = "SECRET-PROMPT-CONTENT"
        for setup in ("http_404", "malformed", "unreachable"):
            if setup == "http_404":
                ollama_stub.status = 404
                ollama_stub.body = b"{}"
                adapter = OllamaAdapter(model="m", base_url=ollama_stub.url)
            elif setup == "malformed":
                ollama_stub.status = 200
                ollama_stub.body = b"nope"
                adapter = OllamaAdapter(model="m", base_url=ollama_stub.url)
            else:
                adapter = OllamaAdapter(
                    model="m", base_url=f"http://127.0.0.1:{_free_port()}",
                    timeout_seconds=1,
                )
            with pytest.raises(AdapterError) as excinfo:
                adapter.generate(secret)
            assert secret not in str(excinfo.value)
