"""Opt-in FFmpeg + HTTP business smoke against tests.smoke_server.

Uses generated local media with embedded subtitles. No ASR model download or
real model call is required; explicit AI fallback must still produce artifacts.
"""
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:18999"


def request(path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    with urlopen(Request(BASE + path, data=body, headers={"Content-Type": "application/json"}), timeout=10) as response:
        return json.load(response)


def main():
    started = time.monotonic()
    with TemporaryDirectory(prefix="vinote-media-smoke-") as directory:
        folder = Path(directory)
        subtitles = folder / "demo.srt"
        subtitles.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\n这是一段本地字幕流程验收。\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n首尾关键事实都应保留，结尾是橙色行星。\n",
            encoding="utf-8",
        )
        media = folder / "subtitle-smoke.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=2",
            "-i", str(subtitles), "-map", "0:v", "-map", "1:s", "-c:v", "libx264",
            "-c:s", "mov_text", "-t", "2", str(media),
        ], check=True, timeout=20)
        task_id = request("/api/process-local-path", {"file_path": str(media), "summary_language": "zh"})["task_id"]
        deadline = time.monotonic() + 30
        while True:
            task = request("/api/task-status/" + task_id)
            if task["status"] in {"completed", "error", "cancelled"}:
                break
            assert time.monotonic() < deadline, "media task timed out"
            time.sleep(0.1)
        assert task["status"] == "completed", task.get("error")
        assert task["warnings"], "unconfigured LLM must have an explicit fallback warning"
        assert "橙色行星" in task["raw_script"] and "橙色行星" in task["script"]
        for field in ("raw_script_filename", "transcript_filename", "summary_filename"):
            with urlopen(BASE + "/download/" + quote(task[field]), timeout=10) as response:
                assert response.status == 200 and response.read()
        assert media.is_file(), "user-provided source media must not be deleted"
        notes = request("/api/tasks/completed?" + urlencode({"search": "橙色行星"}))
        assert notes["total"] == 1, "new note must be indexed after persistence"
        print("PASS: embedded subtitles -> note generation with explicit AI fallback -> SQLite/full-text search -> artifact downloads")
        print(f"Media HTTP smoke elapsed: {time.monotonic() - started:.2f}s; source preserved; no real LLM/ASR used.")


if __name__ == "__main__":
    main()
