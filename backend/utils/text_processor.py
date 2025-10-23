"""
文本处理工具函数
统一的文本处理逻辑，消除重复代码
"""
import re
from typing import List


def detect_language(text: str) -> str:
    """
    检测文本语言
    优先从标记提取，其次字符统计
    
    Args:
        text: 输入文本
        
    Returns:
        语言代码 (zh/en/ja/ko等)
    """
    # 1. 从标记提取
    if "**检测语言:**" in text or "**Detected Language:**" in text:
        lines = text.split('\n')
        for line in lines:
            if "**检测语言:**" in line or "**Detected Language:**" in line:
                lang = line.split(":")[-1].strip()
                return lang
    
    # 2. 字符统计
    total_chars = len(text)
    if total_chars == 0:
        return "en"
    
    # 统计各语言字符
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))
    korean_chars = len(re.findall(r'[\uac00-\ud7af]', text))
    
    # 计算比例
    chinese_ratio = chinese_chars / total_chars
    japanese_ratio = japanese_chars / total_chars
    korean_ratio = korean_chars / total_chars
    
    # 判断语言
    if chinese_ratio > 0.1:
        return "zh"
    elif japanese_ratio > 0.05:
        return "ja"
    elif korean_ratio > 0.05:
        return "ko"
    else:
        return "en"


def estimate_tokens(text: str, include_overhead: bool = True) -> int:
    """
    估算文本的token数量
    
    Args:
        text: 输入文本
        include_overhead: 是否包含系统提示词开销
    
    Returns:
        估算的token数
    """
    # 计算中文字符
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    
    # 计算英文单词
    english_words = len([word for word in text.split() if word.isascii() and word.isalpha()])
    
    # 基础tokens
    base_tokens = chinese_chars * 1.5 + english_words * 1.3
    
    # 格式开销（Markdown等）
    format_overhead = len(text) * 0.15
    
    # 系统提示词开销
    system_overhead = 2500 if include_overhead else 0
    
    return int(base_tokens + format_overhead + system_overhead)


def smart_chunk_text(
    text: str,
    max_chars_per_chunk: int = 4000,
    prefer_paragraphs: bool = True
) -> List[str]:
    """
    智能分块文本
    
    Args:
        text: 要分块的文本
        max_chars_per_chunk: 每块最大字符数
        prefer_paragraphs: 优先按段落分割
    
    Returns:
        文本块列表
    """
    chunks = []
    
    if prefer_paragraphs:
        # 优先按段落分割
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        current_chunk = ""
        
        for para in paragraphs:
            candidate = (current_chunk + "\n\n" + para).strip() if current_chunk else para
            
            if len(candidate) > max_chars_per_chunk and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                current_chunk = candidate
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
    else:
        # 按句子分割
        sentences = re.split(r'[.!?。！？]\s+', text)
        current_chunk = ""
        
        for sent in sentences:
            candidate = (current_chunk + ". " + sent).strip() if current_chunk else sent
            
            if len(candidate) > max_chars_per_chunk and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sent
            else:
                current_chunk = candidate
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
    
    # 对仍然过长的块进行二次分割
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_chars_per_chunk:
            final_chunks.append(chunk)
        else:
            # 按句子边界强制分割
            final_chunks.extend(_force_split_chunk(chunk, max_chars_per_chunk))
    
    return final_chunks


def _force_split_chunk(chunk: str, max_chars: int) -> List[str]:
    """强制分割超长块"""
    result = []
    pos = 0
    
    while pos < len(chunk):
        end = min(pos + max_chars, len(chunk))
        
        if end < len(chunk):
            # 寻找句子边界
            for ending in ['。', '！', '？', '.', '!', '?']:
                idx = chunk.rfind(ending, pos, end)
                if idx > pos + int(max_chars * 0.7):
                    end = idx + 1
                    break
            else:
                # 次选：空格边界
                space_idx = chunk.rfind(' ', pos, end)
                if space_idx > pos + int(max_chars * 0.8):
                    end = space_idx
        
        result.append(chunk[pos:end].strip())
        pos = end
    
    return [r for r in result if r]


def format_markdown_paragraphs(text: str) -> str:
    """
    确保Markdown段落格式正确
    
    Args:
        text: 输入文本
        
    Returns:
        格式化后的文本
    """
    if not text:
        return text
    
    # 统一换行符
    formatted = text.replace("\r\n", "\n")
    
    # 标题后加空行
    formatted = re.sub(r"(^#{1,6}\s+.*)\n([^\n#])", r"\1\n\n\2", formatted, flags=re.M)
    
    # 压缩多余空行（≥3个换行 → 2个）
    formatted = re.sub(r"\n{3,}", "\n\n", formatted)
    
    # 去除首尾空行
    formatted = formatted.strip()
    
    return formatted


def remove_transcript_headings(text: str) -> str:
    """
    移除转录文本标题
    
    Args:
        text: 输入文本
        
    Returns:
        移除标题后的文本
    """
    if not text:
        return text
    
    lines = text.split('\n')
    filtered = []
    
    for line in lines:
        stripped = line.strip()
        # 移除 "# Transcript" 等标题
        if re.match(r"^#{1,6}\s*transcript(\s+text)?\s*$", stripped, flags=re.I):
            continue
        filtered.append(line)
    
    return '\n'.join(filtered)


def enforce_paragraph_length(text: str, max_chars: int = 400) -> str:
    """
    确保段落不超过指定长度
    
    Args:
        text: 输入文本
        max_chars: 段落最大字符数
        
    Returns:
        处理后的文本
    """
    if not text:
        return text
    
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    result_paragraphs = []
    
    for para in paragraphs:
        if len(para) <= max_chars:
            result_paragraphs.append(para)
        else:
            # 按句子分割长段落
            result_paragraphs.extend(_split_long_paragraph(para, max_chars))
    
    return "\n\n".join(result_paragraphs)


def _split_long_paragraph(para: str, max_chars: int) -> List[str]:
    """分割超长段落"""
    sentences = re.split(r'([.!?。！？]\s+)', para)
    
    # 重组句子（保留标点）
    complete_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            complete_sentences.append(sentences[i] + sentences[i + 1])
        else:
            complete_sentences.append(sentences[i])
    
    # 按长度限制组合
    result = []
    current = ""
    
    for sent in complete_sentences:
        candidate = (current + " " + sent).strip() if current else sent
        
        if len(candidate) > max_chars and current:
            result.append(current.strip())
            current = sent
        else:
            current = candidate
    
    if current.strip():
        result.append(current.strip())
    
    return result
