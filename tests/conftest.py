import pytest

from prompt_registry.models import VariableSpec
from prompt_registry.store import RegistryStore


@pytest.fixture
def store(tmp_path):
    with RegistryStore.create(tmp_path / "registry.db") as s:
        yield s


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
