#!/usr/bin/env python3
"""Validate source-level invariants required for a ViNote release."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.4.0"


def read(relative_path: str, errors: list[str]) -> str:
    try:
        return (ROOT / relative_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        errors.append(f"{relative_path}: missing or unreadable")
        return ""


def parse_env_example(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_project_version(text: str) -> str | None:
    """Read project.version without requiring tomllib on Python 3.10."""
    section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        section_match = re.fullmatch(r"\[([^]]+)\]\s*(?:#.*)?", line)
        if section_match:
            section = section_match.group(1).strip()
            continue
        if section != "project":
            continue
        version_match = re.fullmatch(r"version\s*=\s*([\"'])(.*?)\1\s*(?:#.*)?", line)
        if version_match:
            return version_match.group(2)
    return None


def require_contains(text: str, marker: str, message: str, errors: list[str]) -> None:
    if marker not in text:
        errors.append(message)


def active_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def active_batch_lines(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith("::")
        and not re.match(r"\s*rem(?:\s|$)", line, re.IGNORECASE)
    )


def imported_name(tree: ast.AST, module: str, name: str) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == module
        and any(alias.name == name for alias in node.names)
        for node in ast.walk(tree)
    )


def class_assignment(tree: ast.Module, class_name: str, target_name: str) -> ast.expr | None:
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                if statement.target.id == target_name:
                    return statement.value
            if isinstance(statement, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == target_name for target in statement.targets):
                    return statement.value
    return None


def getenv_has_default(node: ast.expr | None, key: str, default: str) -> bool:
    if node is None:
        return False
    return any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "os"
        and call.func.attr == "getenv"
        and len(call.args) >= 2
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == key
        and isinstance(call.args[1], ast.Constant)
        and call.args[1].value == default
        for call in ast.walk(node)
    )


def validate_python_sources(errors: list[str]) -> None:
    sources = {
        path: read(path, errors)
        for path in (
            "backend/version.py",
            "backend/main.py",
            "backend/config/settings.py",
            "backend/config/ai_config.py",
        )
    }
    trees: dict[str, ast.Module] = {}
    for path, text in sources.items():
        if not text:
            continue
        try:
            trees[path] = ast.parse(text, filename=path)
        except SyntaxError:
            errors.append(f"{path}: invalid Python syntax")

    version_tree = trees.get("backend/version.py")
    if version_tree is not None:
        assignments = {
            target.id: node.value
            for node in version_tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        fallback = assignments.get("FALLBACK_VERSION")
        package = assignments.get("PACKAGE_NAME")
        resolved = assignments.get("VERSION")
        resolver = next(
            (node for node in version_tree.body if isinstance(node, ast.FunctionDef) and node.name == "resolve_version"),
            None,
        )
        resolver_strings = {
            node.value for node in ast.walk(resolver) if isinstance(node, ast.Constant) and isinstance(node.value, str)
        } if resolver else set()
        has_metadata_lookup = bool(resolver) and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "metadata"
            and node.func.attr == "version"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "PACKAGE_NAME"
            for node in ast.walk(resolver)
        )
        valid_version_module = (
            isinstance(fallback, ast.Constant)
            and fallback.value == EXPECTED_VERSION
            and isinstance(package, ast.Constant)
            and package.value == "vinote"
            and isinstance(resolved, ast.Call)
            and isinstance(resolved.func, ast.Name)
            and resolved.func.id == "resolve_version"
            and {"VERSION", "pyproject.toml"}.issubset(resolver_strings)
            and has_metadata_lookup
        )
        if not valid_version_module:
            errors.append("backend/version.py: source, package metadata, and fallback resolution are not correctly wired")

    main_tree = trees.get("backend/main.py")
    main_wired = bool(main_tree) and imported_name(main_tree, "backend.version", "VERSION") and any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "FastAPI"
        and any(keyword.arg == "version" and isinstance(keyword.value, ast.Name) and keyword.value.id == "VERSION" for keyword in node.keywords)
        for node in ast.walk(main_tree)
    )
    if not main_wired:
        errors.append("backend/main.py: FastAPI version must use backend.version.VERSION")

    settings_tree = trees.get("backend/config/settings.py")
    settings_version = class_assignment(settings_tree, "Settings", "APP_VERSION") if settings_tree else None
    if not settings_tree or not imported_name(settings_tree, "backend.version", "VERSION") or not (
        isinstance(settings_version, ast.Name) and settings_version.id == "VERSION"
    ):
        errors.append("backend/config/settings.py: APP_VERSION must use backend.version.VERSION")
    port_value = class_assignment(settings_tree, "Settings", "PORT") if settings_tree else None
    if not getenv_has_default(port_value, "APP_PORT", "8999"):
        errors.append("backend/config/settings.py: APP_PORT fallback must be 8999")

    ai_tree = trees.get("backend/config/ai_config.py")
    max_input = class_assignment(ai_tree, "ASRConfig", "max_input_seconds") if ai_tree else None
    openai_model = class_assignment(ai_tree, "OpenAIConfig", "model") if ai_tree else None
    if not isinstance(max_input, ast.Constant) or max_input.value != 60:
        errors.append("backend/config/ai_config.py: ASR max input fallback must be 60")
    if not isinstance(openai_model, ast.Constant) or openai_model.value != "gpt-4o":
        errors.append("backend/config/ai_config.py: OpenAI model fallback must be gpt-4o")
    ai_constants = {node.value for node in ast.walk(ai_tree) if isinstance(node, ast.Constant)} if ai_tree else set()
    if not {"ASR_MODEL", "WHISPER_MODEL_SIZE", "whisper"}.issubset(ai_constants):
        errors.append("backend/config/ai_config.py: Whisper legacy override compatibility is missing")


def validate_launchers(errors: list[str]) -> None:
    unix = read("start.sh", errors)
    unix_active = active_lines(unix)
    for marker, description in (
        ("set -Eeuo pipefail", "strict shell mode"),
        ("uv sync --frozen", "locked backend install"),
        ("npm ci", "locked frontend install"),
        ("VERSION", "VERSION-derived banner"),
        ("uv run python", "uv-managed ANP launch"),
    ):
        require_contains(unix_active, marker, f"start.sh: missing {description}", errors)
    if re.search(r"\bkill\s+-9\b", unix_active):
        errors.append("start.sh: must not force-kill an unrelated port owner")
    if re.search(r"^\s*(?:source|\.)\s+\.env\b", unix_active, re.MULTILINE):
        errors.append("start.sh: must not execute .env as shell code")
    cleanup = re.search(r"cleanup\s*\(\)\s*\{(?P<body>.*?)^\}", unix_active, re.MULTILINE | re.DOTALL)
    cleanup_body = cleanup.group("body") if cleanup else ""
    preserves_status = (
        "$1" in cleanup_body
        and re.search(r"\bexit\s+[\"']?\$\{?(?:status|exit_status|exit_code)\}?", cleanup_body)
        and re.search(r"\btrap\b[^\n]*cleanup[^\n]*\$\?", unix_active)
    )
    if not preserves_status:
        errors.append("start.sh: cleanup must accept and preserve the triggering exit status")

    windows = read("start.bat", errors)
    windows_lower = active_batch_lines(windows).lower()
    for marker, description in (
        ("uv sync --frozen", "locked backend install"),
        ("npm ci", "locked frontend install"),
        ("if errorlevel 1", "command failure handling"),
        ("version", "VERSION-derived banner"),
        ("uv run python", "uv-managed ANP launch"),
    ):
        if marker not in windows_lower:
            errors.append(f"start.bat: missing {description}")
    if "正在释放" in windows:
        errors.append("start.bat: must not kill the process that already owns the configured port")


def validate_deployment_and_docs(errors: list[str]) -> None:
    dockerfile = read("Dockerfile", errors)
    dockerfile_active = active_lines(dockerfile)
    version_copy = any(
        re.match(r"\s*COPY(?:\s+--\S+)*\s+.*\bVERSION\b", line, re.IGNORECASE)
        for line in dockerfile_active.splitlines()
    )
    if not version_copy:
        errors.append("Dockerfile: VERSION is not copied into the image")
    if re.search(r"pip\s+install\s+--upgrade\s+yt-dlp", dockerfile_active):
        errors.append("Dockerfile: yt-dlp must remain locked by the release lockfile")

    compose = read("docker-compose.yml", errors)
    if any(
        "bilibili_cookies.txt:/app/bilibili_cookies.txt" in line
        for line in compose.splitlines()
        if not line.lstrip().startswith("#")
    ):
        errors.append("docker-compose.yml: example cookie bind must not be active by default")

    readme = read("README.md", errors)
    for marker, description in (
        ("docker compose up -d --build", "image rebuild command"),
        ("./start.sh", "Unix launcher command"),
        ("start.bat", "Windows launcher command"),
        ("curl -f http://localhost:8999/health", "health-check command"),
        ("20.19", "Node 20.19 guidance"),
        ("22.12", "Node 22.12 guidance"),
        ("http://localhost:8000/ad.json", "host ANP URL"),
        ("host.docker.internal", "container ANP host guidance"),
        ("--workers 1", "single-worker guidance"),
    ):
        require_contains(readme, marker, f"README.md: missing {description}", errors)
    if "http://localhost:8999/ad.json" in readme:
        errors.append("README.md: contains the obsolete ANP URL")
    if "--workers 4" in readme:
        errors.append("README.md: contains unsafe multi-worker guidance")


def main() -> int:
    errors: list[str] = []
    version_text = read("VERSION", errors)
    if version_text.splitlines() != [EXPECTED_VERSION]:
        errors.append("VERSION: must contain only 1.4.0")

    pyproject = read("pyproject.toml", errors)
    if parse_project_version(pyproject) != EXPECTED_VERSION:
        errors.append("pyproject.toml: project version must be 1.4.0")

    env_values = parse_env_example(read(".env.example", errors))
    expected_env = {
        "APP_HOST": "0.0.0.0",
        "APP_PORT": "8999",
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_MODEL": "gpt-4o",
        "ASR_PROVIDER": "whisper",
        "ASR_MODEL": "base",
        "ASR_MODEL_SOURCE": "huggingface",
        "ASR_MODEL_DIR": "",
        "ASR_DEVICE": "cpu",
        "ASR_COMPUTE_TYPE": "int8",
        "ASR_MAX_INPUT_SECONDS": "60",
        "ASR_MAX_INFERENCE_BATCH_SIZE": "1",
        "ANP_SERVER_URL": "http://localhost:8000/ad.json",
        "VIDEO_SEARCH_PROVIDERS": "local",
        "BATCH_CONCURRENCY": "5",
        "ASR_CONCURRENCY": "1",
    }
    for key, expected in expected_env.items():
        if env_values.get(key) != expected:
            errors.append(f".env.example: {key} has an invalid release default")
    if "WHISPER_MODEL_SIZE" in env_values:
        errors.append(".env.example: WHISPER_MODEL_SIZE must remain commented legacy compatibility only")

    validate_python_sources(errors)
    validate_launchers(errors)
    validate_deployment_and_docs(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("release validation: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
