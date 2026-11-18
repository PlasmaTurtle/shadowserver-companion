"""Direct shared JSON-contract tests, independent of workflows and providers."""

import json
import sys

import pytest

from workbench.aegis.json import strict_json_decoder, strict_json_loads


@pytest.mark.parametrize(
    "body",
    [
        b'{"a":1,"a":2}',
        b'{"x":{"a":1,"a":2}}',
        b'{"n":NaN}',
        b'{"n":Infinity}',
        b'{"n":-Infinity}',
        b'{"n":1e999}',
        b'"\\ud800"',
        b'{"\\udfff":1}',
        b"\xff",
        b'{"x":1} trailing',
    ],
)
def test_rejects_ambiguous_nonfinite_or_invalid_text(body):
    with pytest.raises(ValueError):
        strict_json_loads(body)


def test_supported_values_and_explicit_object_policy():
    raw = '{"name":"Café 😀","nested":[true,null,1,0.2]}'
    expected = json.loads(raw)
    assert strict_json_loads(raw.encode()) == expected
    assert strict_json_loads(bytearray(raw.encode())) == expected
    assert strict_json_loads("\ufeff" + raw) == expected
    assert strict_json_loads(b"\xef\xbb\xbf" + raw.encode()) == expected
    assert strict_json_loads("[1,2]") == [1, 2]
    with pytest.raises(ValueError, match="object"):
        strict_json_loads("[1,2]", require_object=True)
    assert strict_json_loads('"\\ud83d\\ude00"') == "😀"


@pytest.mark.parametrize("body", [b'{"x":1}' + b" " * 100, '{"x":"éééé"}'])
def test_byte_budget_counts_utf8_and_trailing_whitespace(body):
    with pytest.raises(ValueError, match="byte limit"):
        strict_json_loads(body, max_bytes=15)
    text = body.decode() if isinstance(body, bytes) else body
    with pytest.raises(ValueError, match="byte limit"):
        strict_json_decoder(max_bytes=15).decode(text)


def test_depth_preflight_runs_before_recursive_decoder_and_ignores_string_braces():
    assert strict_json_loads('{"value":"[[[{{{]}}}"}', max_depth=1) == {"value": "[[[{{{]}}}"}
    with pytest.raises(ValueError, match="nesting"):
        strict_json_loads("[" * 2000 + "0" + "]" * 2000, max_depth=32)
    assert strict_json_loads("[[0]]", max_depth=2) == [[0]]
    with pytest.raises(ValueError, match="nesting"):
        strict_json_loads("[[[0]]]", max_depth=2)


def test_streaming_decoder_bounds_current_record_without_consuming_next():
    decoder = strict_json_decoder(max_bytes=10, max_depth=2)
    value, end = decoder.raw_decode('{"x":1},' + " " * 10000)
    assert value == {"x": 1} and end == 7
    assert strict_json_decoder(max_bytes=4).raw_decode("null,remaining") == (None, 4)
    assert strict_json_decoder(max_bytes=4).raw_decode("true]remaining") == (True, 4)
    with pytest.raises(json.JSONDecodeError):
        decoder.raw_decode('{"x":')
    with pytest.raises(ValueError, match="byte limit"):
        decoder.raw_decode('{"xxxxxxxxxxxx":')
    with pytest.raises(ValueError, match="nesting"):
        decoder.raw_decode("[[[")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_bytes": 0},
        {"max_bytes": True},
        {"max_depth": 0},
        {"max_depth": True},
        {"max_depth": 100000},
    ],
)
def test_invalid_limit_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        strict_json_loads("{}", **kwargs)


def test_json_module_has_no_domain_dependency():
    import ast
    from pathlib import Path
    from workbench.aegis import json as boundary

    tree = ast.parse(Path(boundary.__file__).read_text())
    assert not any(isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(tree))
    assert not any(
        isinstance(node, ast.Import)
        and any(n.name.startswith(("workbench", "attribution")) for n in node.names)
        for node in ast.walk(tree)
    )
