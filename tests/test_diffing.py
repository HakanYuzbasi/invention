from prompt_registry.diffing import diff_versions
from prompt_registry.models import PromptVersion, VariableSpec, compute_content_hash


def make_version(version, body, variables=()):
    return PromptVersion(
        prompt_id="p",
        version=version,
        body=body,
        variables=tuple(variables),
        note="",
        content_hash=compute_content_hash(body, tuple(variables)),
        created_at="2026-07-18T00:00:00+00:00",
    )


def test_identical_versions():
    a = make_version(1, "same {{ x }}", [VariableSpec(name="x")])
    b = make_version(2, "same {{ x }}", [VariableSpec(name="x")])
    report = diff_versions(a, b)
    assert report.identical
    assert "identical" in report.render_text()


def test_body_diff_is_unified(sample_prompt=None):
    a = make_version(1, "line one\nline two\n")
    b = make_version(2, "line one\nline 2\n")
    report = diff_versions(a, b)
    assert not report.identical
    assert "-line two" in report.body_diff
    assert "+line 2" in report.body_diff
    assert "p@v1" in report.body_diff and "p@v2" in report.body_diff


def test_variable_schema_delta():
    a = make_version(
        1, "{{ a }} {{ b }}",
        [VariableSpec(name="a"), VariableSpec(name="b", required=False, default="1")],
    )
    b = make_version(
        2, "{{ b }} {{ c }}",
        [VariableSpec(name="b", required=False, default="2"), VariableSpec(name="c")],
    )
    report = diff_versions(a, b)
    changes = "\n".join(report.variable_changes)
    assert "- removed a (required)" in changes
    assert "+ added c (required)" in changes
    assert "~ changed b (optional, default='1') -> b (optional, default='2')" in changes


def test_unchanged_body_with_changed_vars():
    # only defaults differ; body identical
    a = make_version(1, "{{ x }}", [VariableSpec(name="x", required=False, default="a")])
    b = make_version(2, "{{ x }}", [VariableSpec(name="x", required=False, default="b")])
    report = diff_versions(a, b)
    assert not report.identical
    assert report.body_diff == ""
    assert report.variable_changes
    assert "(body unchanged)" in report.render_text()
