"""问答资料的本地词法召回：有界上下文、每来源配额和稳定片段编号。"""
import math
import re
from collections import Counter

from backend.utils.text_processor import smart_chunk_text

MAX_CONTEXT_CHARS = 24000
MAX_HISTORY_CHARS = 12000
MAX_TRANSCRIPT_CHARS = 500000
CHUNK_CHARS = 1200

_STOP_TERMS = {
    "请问", "什么", "如何", "这个", "视频", "内容", "主要", "一下", "总结",
    "以及", "哪些", "介绍", "说明", "根据", "告诉", "我们", "可以", "是否",
    "一个", "the", "a", "an", "of", "to", "and", "is", "are", "in", "it",
    "this", "that", "what", "how", "please", "video", "summarize",
}


def _terms(text: str) -> set[str]:
    terms: set[str] = set()
    for word in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        if "\u4e00" <= word[0] <= "\u9fff":
            terms.update(word[i:i + 2] for i in range(max(1, len(word) - 1)))
        else:
            terms.add(word)
    return terms - _STOP_TERMS


def _spread_indices(length: int, count: int) -> list[int]:
    count = min(length, max(1, count))
    if count == 1:
        return [length // 2]
    return [round(i * (length - 1) / (count - 1)) for i in range(count)]


def retrieval_query(question: str, history: list[dict] | None = None) -> str:
    """为“那它呢”等追问补充近期用户主题，不把旧模型答案当成证据。"""
    recent_questions = [
        str(message.get("content") or "")[-1000:]
        for message in (history or [])[-6:]
        if message.get("role") == "user"
    ][-2:]
    return "\n".join([question, *recent_questions])


def bounded_history(history: list[dict] | None, max_chars: int = MAX_HISTORY_CHARS) -> list[dict]:
    """保留最近消息，同时约束总长度，避免长会话挤占来源上下文。"""
    remaining = max(0, max_chars)
    selected = []
    for message in reversed((history or [])[-12:]):
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content or not remaining:
            continue
        excerpt = content[-min(4000, remaining):]
        selected.append({"role": role, "content": excerpt})
        remaining -= len(excerpt)
    return list(reversed(selected))


def build_qa_context(
    sources: list[dict], question: str, max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """从每篇完整资料召回相关片段；返回值连同标题、编号都不超过预算。

    sources 的 content/title/short_id 只在内存中使用，不建立外部索引。
    片段编号由原文顺序决定，问题变化后仍能对应同一笔记片段。
    """
    available = [source for source in sources if str(source.get("content") or "").strip()]
    if not available:
        return ""
    if max_chars < 256 * len(available):
        raise ValueError("上下文预算不足以覆盖所选来源")

    query_terms = _terms(question)
    documents = []
    frequencies: Counter[str] = Counter()
    total_chunks = 0
    for source in available:
        chunks = smart_chunk_text(str(source["content"]), CHUNK_CHARS)
        matches = []
        for chunk in chunks:
            matched = query_terms & _terms(chunk)
            matched.update(term for term in query_terms if len(term) == 1 and term in chunk.lower())
            matches.append(matched)
            frequencies.update(matched)
        total_chunks += len(chunks)
        documents.append((source, chunks, matches))

    separator = "\n\n---\n\n"
    source_budget = (max_chars - len(separator) * (len(documents) - 1)) // len(documents)
    sections = []
    for source_index, (source, chunks, matches) in enumerate(documents, 1):
        title = " ".join(str(source.get("title") or "视频内容").split())[:120]
        note_id = str(source.get("short_id") or "").strip()[:64]
        header = f"## 来源{source_index}：{title}"
        if note_id:
            header += f"（笔记 {note_id}）"
        header += "\n"
        remaining = source_budget - len(header)
        slots = max(1, remaining // (CHUNK_CHARS + 32))
        scores = [
            sum(1 + math.log((total_chunks + 1) / (frequencies[term] + 1)) for term in matched)
            for matched in matches
        ]
        ranked = sorted(range(len(chunks)), key=lambda index: (-scores[index], index))
        relevant = [index for index in ranked if scores[index] > 0]
        # 优先相关证据，至少留一个位置给全文代表片段；无关键词时均匀覆盖首中尾。
        candidates = relevant[:max(1, slots - 1)] + _spread_indices(len(chunks), slots) + ranked
        selected: dict[int, str] = {}
        for index in candidates:
            if index in selected:
                continue
            label = f"[来源{source_index}·片段{index + 1}]\n"
            piece = label + chunks[index]
            cost = len(piece) + (2 if selected else 0)
            if cost > remaining:
                if selected:
                    continue
                # 极小预算也必须保留当前来源的至少一个片段。
                piece = piece[:remaining]
                cost = len(piece)
            selected[index] = piece
            remaining -= cost
        sections.append(header + "\n\n".join(selected[index] for index in sorted(selected)))
    return separator.join(sections)
