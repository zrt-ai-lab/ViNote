import asyncio
import logging
from typing import Any, Dict, List

from backend.services.search_providers.base import SearchProvider
from backend.services.search_providers.local_provider import LocalSearchProvider

logger = logging.getLogger(__name__)


class SearchProviderManager:

    def __init__(self):
        self.providers: List[SearchProvider] = []
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        provider = LocalSearchProvider()
        try:
            if await provider.initialize():
                self.providers.append(provider)
            else:
                logger.warning("Direct video search initialization failed")
        except Exception:
            logger.exception("Failed to initialize direct video search")

        self._initialized = True
        logger.info(f"SearchProviderManager ready — active providers: {[p.name for p in self.providers]}")

    async def execute_search(self, query: str, **kwargs) -> Dict[str, Any]:
        await self.initialize()

        if not self.providers:
            return {
                "success": False,
                "error": "No search providers available",
                "results": [],
                "count": 0,
                "providers": [],
            }

        all_results = []
        providers_used = []
        errors = []
        error_codes = []

        tasks = [p.search(query, **kwargs) for p in self.providers]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for provider, outcome in zip(self.providers, outcomes):
            if isinstance(outcome, Exception):
                logger.warning("Search provider '%s' failed (%s)", provider.name, type(outcome).__name__)
                errors.append(provider.name)
                error_codes.append('unavailable')
                continue
            if outcome.get("success"):
                all_results.extend(outcome.get("results", []))
                providers_used.append(provider.name)
            else:
                logger.warning(
                    "Search provider '%s' returned an error: %s",
                    provider.name,
                    outcome.get("error", "unknown"),
                )
                errors.append(provider.name)
                error_codes.append(outcome.get('error_code', 'unavailable'))

        seen_urls = set()
        deduplicated = []
        for v in all_results:
            url = v.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduplicated.append(v)

        success = len(deduplicated) > 0 or not errors
        messages = {
            'invalid_response': '视频平台返回了非数据页面，请检查网络或 Cookie 后重试',
            'platform_restricted': '视频平台限制了当前请求，请稍后重试或检查 Cookie',
            'timeout': '视频搜索超时，请稍后重试',
            'invalid_query': '搜索关键词不正确，请使用 1–200 字的关键词',
            'invalid_page': '搜索页码不正确',
            'invalid_limit': '每页结果数量不正确',
            'unsupported_platform': '暂不支持该平台的关键词搜索',
            'dependency_unavailable': '搜索依赖不可用，请重新安装项目依赖',
        }
        code = error_codes[0] if error_codes else None
        return {
            "success": success,
            "results": deduplicated,
            "count": len(deduplicated),
            "providers": providers_used,
            "error": None if success else messages.get(code, "视频搜索服务暂时不可用"),
            "error_code": None if success else code,
            "failed_providers": errors,
        }
