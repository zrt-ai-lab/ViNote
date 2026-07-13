#!/usr/bin/env python3
"""Scan tracked release sources without echoing sensitive values."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SKIPPED_PREFIXES = ("docs/superpowers/",)
SKIPPED_PATHS = {"scripts/scan_release.py"}
PUBLIC_OPENAI_MODELS = {
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "o1",
    "o1-mini",
    "o3",
    "o3-mini",
    "o4-mini",
}
PLACEHOLDER_VALUES = {
    "",
    "none",
    "null",
    "unset",
    "placeholder",
    "redacted",
    "changeme",
    "replace-me",
    "replace_me",
    "dummy",
    "dummy-key",
    "dummy_key",
    "example",
    "example-key",
    "example_key",
    "your-api-key",
    "your-api-key-here",
    "your_api_key",
    "your_api_key_here",
}
PLACEHOLDER_PATTERNS = (
    re.compile(r"<[^<>]+>"),
    re.compile(r"(?:sk-)?x{8,}"),
    re.compile(r"your_(?:sessdata|bili_jct|dedeuserid|buvid[34]?)(?:_here)?(?:_x+)?"),
    re.compile(r"你的(?:sessdata值（必需）|bili_jct值|用户id)"),
    re.compile(r"用户id"),
    re.compile(r"设备指纹"),
)
LIVE_PREFIX = re.compile(
    r"(?:\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}\b|"
    r"\bsk-ant-[A-Za-z0-9_-]{16,}\b|\bghp_[A-Za-z0-9]{20,}\b|"
    r"\bgithub_pat_[A-Za-z0-9_]{20,}\b|\bhf_[A-Za-z0-9]{20,}\b|"
    r"\bAIza[A-Za-z0-9_-]{25,}\b|\bAKIA[A-Z0-9]{16}\b|"
    r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b)"
)
ASSIGNMENT = re.compile(
    r"(?i)[\"']?(?P<key>[A-Z0-9_-]*(?:API[_-]?KEY|ACCESS[_-]?TOKEN|SECRET[_-]?KEY))[\"']?"
    r"\s*[:=]\s*(?P<value>[^\s,;#]+)"
)
OPENAI_SETTING = re.compile(
    r"[\"']?(?P<key>OPENAI_BASE_URL|OPENAI_MODEL)[\"']?\s*[:=]\s*(?P<value>[^\s,;#]+)"
)
COOKIE = re.compile(
    r"(?i)(?P<key>SESSDATA|bili_jct|DedeUserID|buvid(?:3|4)?)\s*(?:[:=]|\t+)\s*[\"']?(?P<value>(?![\{\[\(])[^\s\"';,]+)"
)
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b")
PERSONAL_PATH = re.compile(r"(?:/Users/[A-Za-z0-9._-]+/|C:\\Users\\[A-Za-z0-9._-]+\\)", re.IGNORECASE)


def clean_value(value: str) -> str:
    return value.strip().strip("\"'`").rstrip(",;")


def is_placeholder(value: str) -> bool:
    lowered = clean_value(value).lower()
    if lowered in PLACEHOLDER_VALUES:
        return True
    if any(pattern.fullmatch(lowered) for pattern in PLACEHOLDER_PATTERNS):
        return True
    if re.fullmatch(r"\$\{[A-Z0-9_]+\}", clean_value(value), re.IGNORECASE):
        return True
    if re.fullmatch(r"%[A-Z0-9_]+%", clean_value(value), re.IGNORECASE):
        return True
    if re.fullmatch(r"optional\[[a-z_][a-z0-9_.]*\]", lowered):
        return True
    if re.fullmatch(r"os\.getenv\([^)]*\)", lowered):
        return True
    if re.fullmatch(r"(?:[a-z_][a-z0-9_]*\.)+[a-z_][a-z0-9_]*", lowered):
        return True
    return False


def is_public_endpoint(value: str) -> bool:
    cleaned = clean_value(value)
    if is_placeholder(cleaned):
        return True
    parsed = urlparse(cleaned if "://" in cleaned else f"//{cleaned}")
    return (parsed.hostname or "").lower() in {"api.openai.com", "localhost", "127.0.0.1"}


def scan_line(path: str, line: str) -> set[str]:
    categories: set[str] = set()
    prefix_match = LIVE_PREFIX.search(line)
    if prefix_match and not is_placeholder(prefix_match.group(0)):
        categories.add("provider-secret")

    for match in ASSIGNMENT.finditer(line):
        value = clean_value(match.group("value"))
        if len(value) >= 8 and not is_placeholder(value):
            categories.add("provider-secret")

    for match in OPENAI_SETTING.finditer(line):
        key = match.group("key").upper()
        value = clean_value(match.group("value"))
        if key == "OPENAI_BASE_URL" and not is_public_endpoint(value):
            categories.add("private-llm-endpoint")
        if key == "OPENAI_MODEL" and not is_placeholder(value) and value not in PUBLIC_OPENAI_MODELS:
            categories.add("private-model-id")

    for match in EMAIL.finditer(line):
        if match.group(1).lower() not in {"qq.com", "example.com", "example.org", "example.net"}:
            categories.add("company-email")

    for match in COOKIE.finditer(line):
        value = match.group("value")
        commented_example = line.lstrip().startswith("#") and "example" in path.lower()
        if not commented_example and not is_placeholder(value):
            categories.add("live-cookie")

    if PERSONAL_PATH.search(line):
        categories.add("personal-absolute-path")
    return categories


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return [item.decode("utf-8", errors="surrogateescape") for item in result.stdout.split(b"\0") if item]


def main() -> int:
    findings: set[tuple[str, str, int]] = set()
    try:
        paths = tracked_paths()
    except (OSError, subprocess.CalledProcessError):
        print("scan-error:git:0")
        return 1

    for relative_path in paths:
        if relative_path in SKIPPED_PATHS or relative_path.startswith(SKIPPED_PREFIXES):
            continue
        source_path = ROOT / relative_path
        if not source_path.is_file():
            continue
        try:
            data = source_path.read_bytes()
        except OSError:
            print(f"scan-error:{relative_path}:0")
            return 1
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for category in scan_line(relative_path, line):
                findings.add((category, relative_path, line_number))

    if findings:
        for category, path, line_number in sorted(findings, key=lambda item: (item[1], item[2], item[0])):
            print(f"{category}:{path}:{line_number}")
        return 1
    print("sensitive scan: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
