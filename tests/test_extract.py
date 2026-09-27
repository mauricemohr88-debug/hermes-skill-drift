import json

from hermes_skill_drift.extract import extract_source


def _capabilities(text, path="cli.py"):
    return extract_source(path, text)


def _keys(result, kind=None):
    return [item["key"] for item in result["capabilities"] if kind is None or item["kind"] == kind]


def _signature(result, key):
    matches = [item for item in result["capabilities"] if item["key"] == key]
    assert len(matches) == 1
    return json.loads(matches[0]["signature"])


def test_ast_only_extraction_does_not_execute_source(capsys):
    result = _capabilities('print("EXECUTED")\nimport os\nos.system("boom")\n')

    assert result["capabilities"] == []
    assert result["warnings"] == []
    assert capsys.readouterr().out == ""


def test_nested_argparse_commands_aliases_and_options():
    text = """
parser = argparse.ArgumentParser(prog="hermes")
subparsers = parser.add_subparsers()
model = subparsers.add_parser("model", aliases=["m"], help="Model help")
model.add_argument("--refresh", action="store_true", help="Refresh help")
model.add_argument("--no-browser", dest="browser", action="store_false")
model_subparsers = model.add_subparsers()
listing = model_subparsers.add_parser("list")
listing.add_argument("--json", default=True, choices=[True, False])
parser.add_argument("--root-only", help="ignored by contract")
"""
    result = _capabilities(text)

    assert _keys(result, "command") == [
        "hermes",
        "hermes m",
        "hermes m list",
        "hermes model",
        "hermes model list",
    ]
    assert _keys(result, "option") == [
        "hermes m --no-browser",
        "hermes m --refresh",
        "hermes m list --json",
        "hermes model --no-browser",
        "hermes model --refresh",
        "hermes model list --json",
    ]
    assert _signature(result, "hermes model --refresh") == {"action": "store_true"}
    assert _signature(result, "hermes model list --json") == {
        "choices": [True, False],
        "default": True,
    }
    assert result["warnings"] == [
        "argparse add_argument outside a tracked command receiver at line 10 "
        "is not statically resolvable"
    ]


def test_receiver_names_do_not_leak_between_function_scopes():
    text = """
def setup_model(subparsers):
    parser = subparsers.add_parser("model")
    parser.add_argument("--refresh", action="store_true")


def setup_status(subparsers):
    parser = subparsers.add_parser("status")
    parser.add_argument("--refresh", default="all")
"""
    result = _capabilities(text)

    assert _keys(result, "command") == ["hermes model", "hermes status"]
    assert _keys(result, "option") == [
        "hermes model --refresh",
        "hermes status --refresh",
    ]
    assert _signature(result, "hermes model --refresh") == {"action": "store_true"}
    assert _signature(result, "hermes status --refresh") == {"default": "all"}


def test_dynamic_argparse_constructs_are_reported_without_invented_keys():
    text = """
def setup(subparsers, name, aliases):
    parser = subparsers.add_parser(name, aliases=aliases)
    other = subparsers.add_parser("other", aliases=aliases)
    other.add_argument(flags)
"""
    result = _capabilities(text)

    assert _keys(result) == ["hermes other"]
    assert (
        "dynamic argparse add_parser at line 3 is not statically resolvable" in result["warnings"]
    )
    assert (
        "dynamic argparse add_parser aliases at line 4 is not statically resolvable"
        in result["warnings"]
    )
    assert (
        "dynamic argparse add_argument flags at line 5 is not statically resolvable"
        in result["warnings"]
    )


def test_dynamic_option_structure_reports_limitation():
    text = """
def setup(subparsers, default):
    parser = subparsers.add_parser("model")
    parser.add_argument("--refresh", default=default)
"""
    result = _capabilities(text)

    assert _keys(result, "option") == ["hermes model --refresh"]
    assert _signature(result, "hermes model --refresh") == {}
    assert (
        "dynamic argparse add_argument structure at line 4 is not statically resolvable"
        in result["warnings"]
    )


def test_helper_receiver_scope_is_not_misattributed_and_warns():
    text = """
def add_common_flags(parser):
    parser.add_argument("--refresh", action="store_true")


def setup(subparsers):
    model = subparsers.add_parser("model")
    add_common_flags(model)
    parser = subparsers.add_parser("status")
    parser.add_argument("--all", action="store_true")
"""
    result = _capabilities(text)

    assert _keys(result, "option") == ["hermes status --all"]
    assert (
        "unresolved argparse add_argument receiver at line 3 is not statically resolvable"
        in result["warnings"]
    )


def test_unsupported_definition_surfaces_warn_instead_of_silent_coverage():
    text = """
def setup(subparsers):
    model = subparsers.add_parser("model")
    model.add_argument("path")
    unknown.add_argument("--unknown")
    root = argparse.ArgumentParser(prog="hermes")
    root.add_argument("--root-only")
"""
    result = _capabilities(text)

    assert _keys(result, "option") == []
    assert (
        "unsupported positional argparse add_argument at line 4 is not statically resolvable"
        in result["warnings"]
    )
    assert (
        "unresolved argparse add_argument receiver at line 5 is not statically resolvable"
        in result["warnings"]
    )
    assert (
        "argparse add_argument outside a tracked command receiver at line 7 "
        "is not statically resolvable" in result["warnings"]
    )


def test_openai_tool_schema_ignores_description_but_keeps_structure():
    schema = """
tool = {
    "type": "function",
    "function": {
        "name": "cronjob",
        "description": "Schedules work",
        "parameters": {
            "type": "object",
            "description": "Wrapper text",
            "properties": {
                "path": {"type": "string", "description": "Path text"},
                "description": {"type": "string", "description": "Field help"},
            },
            "required": ["path"],
        },
    },
}
"""
    changed = schema.replace('"required": ["path"]', '"required": []')
    description_only = schema.replace("Schedules work", "Another purpose")

    result = _capabilities(schema)
    changed_result = _capabilities(changed)
    unchanged_result = _capabilities(description_only)

    assert _keys(result, "tool") == ["cronjob"]
    assert _signature(result, "cronjob") == {
        "properties": {"description": {"type": "string"}, "path": {"type": "string"}},
        "required": ["path"],
        "type": "object",
    }
    assert _signature(result, "cronjob") != _signature(changed_result, "cronjob")
    assert _signature(result, "cronjob") == _signature(unchanged_result, "cronjob")


def test_tool_schemas_require_literal_name_and_parameters():
    text = """
missing_parameters = {"name": "not_a_tool"}
dynamic = {"name": "dynamic_tool", "parameters": build_schema()}
"""
    result = _capabilities(text)

    assert _keys(result, "tool") == ["dynamic_tool"]
    assert result["capabilities"][0]["resolved"] is False
    assert any(
        "dynamic or malformed tool schema at line 3" in warning for warning in result["warnings"]
    )


def test_tool_named_property_is_not_removed_as_metadata():
    result = _capabilities(
        'SCHEMA = {"name":"tool", "parameters":'
        ' {"properties":{"description":{"type":"string"},"help":{"type":"boolean"}}}}\n'
    )

    assert _signature(result, "tool") == {
        "properties": {"description": {"type": "string"}, "help": {"type": "boolean"}}
    }


def test_kwargs_in_argparse_signature_is_unsupported():
    text = """
def setup(subparsers, options):
    parser = subparsers.add_parser("model")
    parser.add_argument("--path", **options)
"""
    result = _capabilities(text)

    assert _signature(result, "hermes model --path") == {}
    assert (
        "dynamic argparse add_argument structure at line 4 is not statically resolvable"
        in result["warnings"]
    )


def test_reassignment_to_unrelated_value_invalidates_receiver():
    text = """
def setup(subparsers):
    parser = subparsers.add_parser("model")
    parser = None
    parser.add_argument("--refresh")
"""
    result = _capabilities(text)

    assert _keys(result, "option") == []
    assert (
        "unresolved argparse add_argument receiver at line 5 is not statically resolvable"
        in result["warnings"]
    )


def test_invalid_unary_literal_fails_closed():
    text = """
valid = {"name":"valid", "parameters":{"value":-1}}
invalid = {"name":"invalid", "parameters":{"value":-"text"}}
"""
    result = _capabilities(text)

    assert _keys(result, "tool") == ["invalid", "valid"]
    assert _signature(result, "valid") == {"value": -1}
    assert (
        "dynamic or malformed tool schema at line 3 is not statically resolvable"
        in result["warnings"]
    )


def test_ordinary_named_dictionary_is_not_a_dynamic_tool_schema():
    result = _capabilities(
        'person = {"name":"Maurice"}\n'
        'openai = {"type":"function", "function":{"name":"not_complete"}}\n'
    )

    assert result == {"capabilities": [], "warnings": []}


def test_builtin_argparse_types_are_symbolic_and_unknown_types_warn():
    text = """
def setup(subparsers, value):
    parser = subparsers.add_parser("model")
    parser.add_argument("--path", type=str)
    parser.add_argument("--count", type=int)
    parser.add_argument("--ratio", type=float)
    parser.add_argument("--decoded", type=decode)
"""
    result = _capabilities(text)

    assert _signature(result, "hermes model --path") == {"type": "str"}
    assert _signature(result, "hermes model --count") == {"type": "int"}
    assert _signature(result, "hermes model --ratio") == {"type": "float"}
    assert _signature(result, "hermes model --decoded") == {}
    assert (
        "dynamic argparse add_argument structure at line 7 is not statically resolvable"
        in result["warnings"]
    )


def test_parse_error_is_reported_without_capabilities():
    result = _capabilities("def broken(:\n", path="broken.py")

    assert result == {
        "capabilities": [],
        "warnings": ["parse error at line 1: invalid syntax"],
    }


def test_schema_annotation_names_in_data_and_definitions_are_preserved():
    from hermes_skill_drift.extract import extract_source

    source = """
schema = {"name": "example", "parameters": {
    "type": "object", "description": "Only metadata",
    "$defs": {"description": {"type": "string"}},
    "properties": {
        "payload": {"const": {"description": "actual-value"}},
        "config": {"enum": [{"help": "a"}, {"help": "b"}]}
    }
}}
"""
    result = extract_source("tools/example.py", source)
    assert not result["warnings"]
    signature = result["capabilities"][0]["signature"]
    assert "Only metadata" not in signature
    assert '"$defs":{"description":{"type":"string"}}' in signature
    assert '"const":{"description":"actual-value"}' in signature
    assert '"enum":[{"help":"a"},{"help":"b"}]' in signature


def test_parser_structure_and_dynamic_parents_are_not_ignored():
    old = _capabilities('def setup(subparsers):\n p=subparsers.add_parser("model")\n')
    new = _capabilities(
        "def setup(subparsers):\n"
        ' p=subparsers.add_parser("model", add_help=False, prefix_chars="+")\n'
    )
    assert _signature(old, "hermes model") != _signature(new, "hermes model")
    dynamic = _capabilities(
        'def setup(subparsers, parent):\n p=subparsers.add_parser("model", parents=[parent])\n'
    )
    assert dynamic["warnings"]
    assert dynamic["capabilities"][0]["resolved"] is False
