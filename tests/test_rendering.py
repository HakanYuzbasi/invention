import pytest

from prompt_registry.errors import RenderError, ValidationError
from prompt_registry.models import VariableSpec
from prompt_registry.rendering import extract_placeholders, render, validate_template


def spec(name, default=None):
    if default is None:
        return VariableSpec(name=name, required=True)
    return VariableSpec(name=name, required=False, default=default)


class TestExtractPlaceholders:
    def test_finds_unique_names_in_order(self):
        body = "{{ a }} then {{b}} then {{ a }} again"
        assert extract_placeholders(body) == ("a", "b")

    def test_ignores_malformed_and_plain_braces(self):
        body = 'JSON: {"key": 1} and {{ 1bad }} and { single } and {{unclosed'
        assert extract_placeholders(body) == ()

    def test_whitespace_tolerant(self):
        assert extract_placeholders("{{  name  }}") == ("name",)


class TestValidateTemplate:
    def test_exact_match_passes(self):
        validate_template("hi {{ a }}", [spec("a")])

    def test_undeclared_placeholder_rejected(self):
        with pytest.raises(ValidationError, match="not declared"):
            validate_template("hi {{ a }} {{ b }}", [spec("a")])

    def test_unused_declaration_rejected(self):
        with pytest.raises(ValidationError, match="not used"):
            validate_template("hi {{ a }}", [spec("a"), spec("b")])

    def test_duplicate_declaration_rejected(self):
        with pytest.raises(ValidationError, match="duplicate"):
            validate_template("hi {{ a }}", [spec("a"), spec("a")])


class TestRender:
    def test_substitutes_values_and_defaults(self):
        body = "task: {{ task }}; tone: {{ tone }}"
        specs = [spec("task"), spec("tone", default="neutral")]
        assert render(body, specs, {"task": "review"}) == "task: review; tone: neutral"
        assert (
            render(body, specs, {"task": "review", "tone": "harsh"})
            == "task: review; tone: harsh"
        )

    def test_missing_required_fails(self):
        with pytest.raises(RenderError, match="missing required variables: task"):
            render("{{ task }}", [spec("task")], {})

    def test_unknown_value_fails(self):
        with pytest.raises(RenderError, match="unknown variables provided: extra"):
            render("{{ task }}", [spec("task")], {"task": "x", "extra": "y"})

    def test_non_string_value_fails(self):
        with pytest.raises(RenderError, match="must be a string"):
            render("{{ task }}", [spec("task")], {"task": 42})

    def test_plain_braces_survive(self):
        body = 'Return JSON like {"ok": true} for {{ x }}'
        assert (
            render(body, [spec("x")], {"x": "it"})
            == 'Return JSON like {"ok": true} for it'
        )

    def test_value_containing_placeholder_syntax_is_not_reexpanded(self):
        # substitution is single-pass by construction
        out = render("{{ x }}", [spec("x")], {"x": "{{ y }}"})
        assert out == "{{ y }}"


class TestVariableSpecInvariants:
    def test_required_with_default_rejected(self):
        with pytest.raises(ValidationError):
            VariableSpec(name="a", required=True, default="x")

    def test_optional_without_default_rejected(self):
        with pytest.raises(ValidationError):
            VariableSpec(name="a", required=False)

    def test_bad_name_rejected(self):
        with pytest.raises(ValidationError):
            VariableSpec(name="1bad")
