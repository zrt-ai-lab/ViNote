"""Parse untrusted model tool arguments as data, never Python expressions."""
import json


def parse_tool_arguments(arguments: str) -> dict:
    parsed = json.loads(arguments)
    if not isinstance(parsed, dict):
        raise ValueError("工具参数必须是 JSON 对象")
    return parsed
