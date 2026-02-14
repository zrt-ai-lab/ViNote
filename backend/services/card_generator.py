"""
知识卡片生成服务

支持 4 种风格：anki(闪卡) / keypoint(要点卡) / concept(概念卡) / cornell(康奈尔笔记)
"""

import json
import logging
import asyncio
from typing import AsyncGenerator, Optional

from backend.config.ai_config import get_openai_config
from backend.core.ai_client import get_openai_client

logger = logging.getLogger(__name__)

STYLE_CONFIGS = {
    "anki": {
        "instruction": """每张卡片必须包含以下 3 个字段（严格 JSON）:
- front: 正面问题（简洁明确的提问，10-30字）
- back: 背面答案（精准简明的回答，20-80字）
- tags: 标签列表（1-3 个关键词标签）

示例:
{{"front": "什么是蛋炒饭的关键火候？", "back": "大火快炒，锅要烧到冒烟再下油，油温够高蛋液才能迅速膨胀包裹米饭", "tags": ["烹饪", "火候"]}}""",
        "required_fields": {"front", "back", "tags"},
        "validate": lambda d: isinstance(d.get("tags"), list),
    },
    "keypoint": {
        "instruction": """每张卡片必须包含以下 6 个字段（严格 JSON）:
- title: 知识点标题（简洁有力，5-15字）
- concept: 核心概念（一个关键词或短语）
- points: 要点列表（3-5 条，每条一句话）
- summary: 一句话总结（不超过 30 字）
- question: 一个检验理解的问题
- answer: 问题的简明答案

示例:
{{"title": "黄金蛋炒饭核心技巧", "concept": "蛋包饭", "points": ["隔夜饭口感更好", "大火快炒是关键", "先炒蛋再下饭"], "summary": "好蛋炒饭靠火候和米饭状态", "question": "为什么要用隔夜饭?", "answer": "水分蒸发颗粒分明不粘连"}}""",
        "required_fields": {"title", "concept", "points", "summary", "question", "answer"},
        "validate": lambda d: isinstance(d.get("points"), list) and len(d["points"]) >= 1,
    },
    "concept": {
        "instruction": """每张卡片必须包含以下 4 个字段（严格 JSON）:
- term: 概念名称（一个关键词或短语，2-8字）
- definition: 概念解释（通俗易懂，30-80字）
- example: 一个具体例子或应用场景（20-60字）
- related: 相关概念列表（2-4 个关联词）

示例:
{{"term": "美拉德反应", "definition": "食物中氨基酸和还原糖在高温下的化学反应，产生香气和焦褐色", "example": "蛋炒饭大火翻炒时米粒表面变金黄", "related": ["焦糖化", "高温烹饪", "风味物质"]}}""",
        "required_fields": {"term", "definition", "example", "related"},
        "validate": lambda d: isinstance(d.get("related"), list),
    },
    "cornell": {
        "instruction": """每张卡片必须包含以下 4 个字段（严格 JSON）:
- cue: 左栏关键词/线索（1-3 个关键词，逗号分隔的字符串）
- notes: 右栏笔记要点列表（3-5 条详细笔记）
- summary: 底部总结（一段话概括，30-60字）
- topic: 主题标题（5-15字）

示例:
{{"cue": "火候, 油温, 翻炒", "notes": ["锅烧到冒烟再下油", "油温要够高蛋液才能膨胀", "全程大火不能减"], "summary": "蛋炒饭的灵魂在于火候控制，大火快炒让蛋液包裹每粒米饭", "topic": "蛋炒饭火候控制"}}""",
        "required_fields": {"cue", "notes", "summary", "topic"},
        "validate": lambda d: isinstance(d.get("notes"), list) and len(d["notes"]) >= 1,
    },
}


class CardGenerator:

    def __init__(self):
        self.config = get_openai_config()
        self.client = get_openai_client()

    def is_available(self) -> bool:
        return self.client is not None

    async def check_content_quality(self, content: str) -> bool:
        if not self.client:
            return True
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.config.model,
                messages=[
                    {"role": "system", "content": "你是内容质量审核员。判断以下文本是否包含可以提取的具体知识点或有价值的信息。\n"
                     "有效内容：课程笔记、技术文档、教程、科普文章、专业讲解、操作步骤等。\n"
                     "无效内容：纯闲聊、无意义字符、重复文字、纯表情、广告spam、过于笼统没有具体信息的文本。\n"
                     "只回复 YES 或 NO，不要解释。"},
                    {"role": "user", "content": content[:2000]},
                ],
                max_tokens=3,
                temperature=0,
            )
            answer = (response.choices[0].message.content or "").strip().upper()
            return answer.startswith("YES")
        except Exception as e:
            logger.warning(f"内容质量检查失败，放行: {e}")
            return True

    async def generate_cards_stream(
        self,
        content: str,
        count: int = 5,
        source: str = "text",
        style: str = "keypoint",
    ) -> AsyncGenerator[dict, None]:
        """
        流式生成知识卡片 (SSE)。

        Args:
            content: 输入文本
            count:   卡片数量 (3-10)
            source:  输入来源 notes / text / qa
            style:   卡片风格 anki / keypoint / concept / cornell
        """
        if not self.client:
            yield {"type": "error", "message": "AI 服务不可用，请检查 OpenAI 配置"}
            return

        content = content.strip()
        if len(content) < 50:
            yield {"type": "error", "message": "内容太短，请提供至少 50 字的文本"}
            return

        count = max(3, min(count, 10))
        style_cfg = STYLE_CONFIGS.get(style, STYLE_CONFIGS["keypoint"])

        is_valid = await self.check_content_quality(content)
        if not is_valid:
            yield {"type": "error", "message": "未提取到有效知识内容。请提供包含具体知识点的文本（如课程笔记、技术文档、教程等），纯闲聊或无意义文本无法生成卡片。"}
            return

        source_hint = {
            "notes": "以下是视频笔记内容",
            "text": "以下是用户提供的文本内容",
            "qa": "以下是视频问答记录",
        }.get(source, "以下是用户提供的文本内容")

        system_prompt = f"""你是一位教育专家和知识整理大师。请从给定内容中提取 {count} 个最重要的知识点，每个知识点生成一张知识卡片。

{style_cfg["instruction"]}

输出格式要求：
- 每张卡片独立一行，输出纯 JSON 对象
- 不要输出 JSON 数组，每行一个独立的 JSON 对象
- 不要添加序号、标记或其他文字
- 不要用 markdown 代码块包裹
- 使用中文"""

        user_prompt = f"""{source_hint}，请提取 {count} 个核心知识点并生成知识卡片：

{content[:8000]}"""

        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4000,
                temperature=0.3,
                stream=True,
            )

            buffer = ""
            card_count = 0

            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    buffer += delta.content

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        card = self._try_parse_card(line, style_cfg)
                        if card:
                            card_count += 1
                            yield {"type": "card", "data": card}

            if buffer.strip():
                card = self._try_parse_card(buffer.strip(), style_cfg)
                if card:
                    card_count += 1
                    yield {"type": "card", "data": card}

            if card_count == 0:
                yield {"type": "error", "message": "未能生成有效的知识卡片，请尝试提供更多内容"}
            else:
                yield {"type": "done"}

        except Exception as e:
            logger.error(f"生成知识卡片失败: {e}")
            yield {"type": "error", "message": f"生成失败: {str(e)}"}

    @staticmethod
    def _try_parse_card(text: str, style_cfg: dict) -> Optional[dict]:
        text = text.strip()
        if not text.startswith("{"):
            idx = text.find("{")
            if idx == -1:
                return None
            text = text[idx:]

        if text.endswith(","):
            text = text[:-1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        if not style_cfg["required_fields"].issubset(data.keys()):
            return None
        if not style_cfg["validate"](data):
            return None

        result = {}
        for key in style_cfg["required_fields"]:
            val = data[key]
            result[key] = [str(item) for item in val] if isinstance(val, list) else str(val)
        return result
