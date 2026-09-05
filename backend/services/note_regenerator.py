"""基于已保存产物重新生成笔记、摘要和思维导图。"""
from datetime import datetime
from pathlib import Path
import re
import uuid

from backend.core.state import TEMP_DIR
from backend.services.content_summarizer import ContentSummarizer
from backend.services.note_repository import get_note, update_note_artifacts
from backend.services.note_operations import cleanup_staging, finish_commit, note_operation
from backend.services.text_optimizer import TextOptimizer


def _artifact_path(filename: str | None) -> Path | None:
    if not filename or Path(filename).name != filename:
        return None
    path = (TEMP_DIR / filename).resolve()
    if path.parent != TEMP_DIR.resolve() or not path.is_file():
        return None
    return path


def _read_artifact(filename: str | None) -> str:
    path = _artifact_path(filename)
    return path.read_text(encoding="utf-8") if path else ""


def _atomic_write(path: Path, content: str) -> None:
    temp_path = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _target_path(existing_filename: str | None, prefix: str, safe_title: str, short_id: str) -> Path:
    existing = _artifact_path(existing_filename)
    if existing:
        return existing
    normalized_title = re.sub(r"[^\w.-]+", "_", safe_title, flags=re.UNICODE).strip("._")
    filename = f"{prefix}_{normalized_title or 'untitled'}_{short_id}.md"
    return TEMP_DIR / filename


async def regenerate_note(short_id: str, targets: list[str], language: str) -> dict:
    async with note_operation(short_id):
        return await _regenerate_note(short_id, targets, language)


async def _regenerate_note(short_id: str, targets: list[str], language: str) -> dict:
    note = await get_note(short_id)
    if not note:
        raise ValueError("笔记不存在")

    title = note.get("title") or "未命名"
    url = note.get("url") or ""
    safe_title = note.get("safe_title") or "untitled"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    optimizer = TextOptimizer()
    summarizer = ContentSummarizer()
    updated: dict[str, str] = {}
    generated_files: dict[Path, str] = {}

    transcript = _read_artifact(note.get("transcript_file"))
    if "transcript" in targets:
        raw = _read_artifact(note.get("raw_transcript_file")) or transcript
        if not raw.strip():
            raise ValueError("没有可用于重新整理的原始转录")
        optimized = await optimizer.optimize_transcript(raw)
        if not optimized.strip():
            raise ValueError("重新整理笔记返回空内容")
        if optimizer.warnings:
            raise ValueError("AI 整理未完整成功，已保留原笔记，请稍后重试")
        transcript = f"# {title}\n\n> 🔗 **视频来源：** [点击观看]({url})\n\n---\n\n{optimized}\n\n---\n\n*整理时间：{now}*  \n*由 ViNote AI 自动生成*\n"
        path = _target_path(note.get("transcript_file"), "transcript", safe_title, short_id)
        generated_files[path] = transcript
        updated["transcript_file"] = path.name

    summary = _read_artifact(note.get("summary_file"))
    if "summary" in targets:
        if not transcript.strip():
            raise ValueError("没有可用于生成摘要的笔记内容")
        generated = await summarizer.summarize(transcript, language, title)
        if not generated.strip():
            raise ValueError("重新生成摘要返回空内容")
        if summarizer.warnings:
            raise ValueError("AI 摘要未完整成功，已保留原笔记，请稍后重试")
        summary = f"# {title}\n\n> 🔗 **视频来源：** [点击观看]({url})\n\n---\n\n{generated}\n\n---\n\n*生成时间：{now}*  \n*由 ViNote AI 自动生成*\n"
        path = _target_path(note.get("summary_file"), "summary", safe_title, short_id)
        generated_files[path] = summary
        updated["summary_file"] = path.name

    if "mindmap" in targets:
        if not summary.strip():
            raise ValueError("没有可用于生成思维导图的摘要")
        mindmap = await summarizer.generate_mindmap(summary, language)
        if not mindmap.strip():
            raise ValueError("重新生成思维导图返回空内容")
        if summarizer.warnings:
            raise ValueError("AI 导图未完整成功，已保留原笔记，请稍后重试")
        path = _target_path(note.get("mindmap_file"), "mindmap", safe_title, short_id)
        generated_files[path] = mindmap
        updated["mindmap_file"] = path.name

    await finish_commit(_commit_artifacts(short_id, generated_files, updated))
    return {"short_id": short_id, "updated": sorted(targets)}


async def _commit_artifacts(short_id: str, generated: dict[Path, str], updated: dict[str, str]) -> None:
    """Stage every new file before replacing originals; rollback only needs renames."""
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    installed: set[Path] = set()
    committed = False
    try:
        for path, content in generated.items():
            stage = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.stage")
            staged[path] = stage
            _atomic_write(stage, content)
        for path, stage in staged.items():
            if path.exists():
                backup = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.backup")
                path.replace(backup)
                backups[path] = backup
            stage.replace(path)
            installed.add(path)
        if not await update_note_artifacts(short_id, **updated):
            raise ValueError("没有可更新的笔记产物")
        committed = True
    except BaseException:
        for path in reversed(staged):
            if path in backups:
                backups[path].replace(path)
            elif path in installed:
                path.unlink(missing_ok=True)
        raise
    finally:
        cleanup_staging(staged.values())
        if committed:
            cleanup_staging(backups.values())
