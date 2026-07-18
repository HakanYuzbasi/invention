import pytest

from prompt_registry.checks import run_check, validate_check
from prompt_registry.errors import ValidationError
from prompt_registry.models import CheckSpec


def outcome(check_type, params, output):
    return run_check(CheckSpec(type=check_type, params=params), output)


class TestContains:
    def test_pass_and_fail(self):
        assert outcome("contains", {"value": "hello"}, "well hello there").passed
        assert not outcome("contains", {"value": "hello"}, "goodbye").passed

    def test_case_insensitive(self):
        params = {"value": "Hello", "case_sensitive": False}
        assert outcome("contains", params, "HELLO world").passed

    def test_not_contains(self):
        assert outcome("not_contains", {"value": "secret"}, "clean output").passed
        assert not outcome("not_contains", {"value": "secret"}, "the secret").passed


class TestRegex:
    def test_multiline_match(self):
        assert outcome("regex", {"pattern": r"^## Summary"}, "intro\n## Summary\n").passed

    def test_no_match_fails(self):
        assert not outcome("regex", {"pattern": r"^\d+$"}, "abc").passed

    def test_not_regex(self):
        assert outcome("not_regex", {"pattern": r"TODO"}, "done").passed
        assert not outcome("not_regex", {"pattern": r"TODO"}, "TODO later").passed


class TestIsJson:
    def test_valid(self):
        assert outcome("is_json", {}, '  {"a": [1, 2]}  ').passed

    def test_invalid(self):
        result = outcome("is_json", {}, "not json at all")
        assert not result.passed
        assert "not valid JSON" in result.message


class TestLength:
    def test_min_length(self):
        assert outcome("min_length", {"value": 3}, "abcd").passed
        assert not outcome("min_length", {"value": 5}, "abcd").passed

    def test_max_length(self):
        assert outcome("max_length", {"value": 5}, "abcd").passed
        assert not outcome("max_length", {"value": 3}, "abcd").passed


class TestValidation:
    def test_unknown_type_rejected(self):
        with pytest.raises(ValidationError, match="unknown check type"):
            validate_check(CheckSpec(type="llm_judge"))

    def test_bad_regex_rejected(self):
        with pytest.raises(ValidationError, match="invalid regex"):
            validate_check(CheckSpec(type="regex", params={"pattern": "("}))

    def test_missing_param_rejected(self):
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_check(CheckSpec(type="contains", params={}))

    def test_bad_length_param_rejected(self):
        with pytest.raises(ValidationError, match="non-negative integer"):
            validate_check(CheckSpec(type="min_length", params={"value": "ten"}))

    def test_is_json_takes_no_params(self):
        with pytest.raises(ValidationError, match="no params"):
            validate_check(CheckSpec(type="is_json", params={"strict": True}))

    def test_bad_case_sensitive_flag_rejected(self):
        with pytest.raises(ValidationError, match="boolean"):
            validate_check(
                CheckSpec(type="contains", params={"value": "x", "case_sensitive": "yes"})
            )
