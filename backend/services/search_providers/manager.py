import asyncio
import logging
from typing import Any, Dict, List

from backend.services.search_providers.base import SearchProvider

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY = {
    "anp": "backend.services.search_providers.anp_provider.ANPSearchProvider",
    "local": "backend.services.search_providers.local_provider.LocalSearchProvider",
}


def _import_provider(dotted_path: str):
    module_path, cls_name = dotted_path.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)


class SearchProviderManager:

    def __init__(self, provider_names: List[str], anp_server_url: str = ""):
        self.provider_names = provider_names
        self.anp_server_url = anp_server_url
        self.providers: List[SearchProvider] = []
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        for name in self.provider_names:
            cls_path = PROVIDER_REGISTRY.get(name)
            if not cls_path:
                logger.warning(f"Unknown search provider: {name}")
                continue

            try:
                cls = _import_provider(cls_path)
                if name == "anp":
                    provider = cls(server_url=self.anp_server_url)
                else:
                    provider = cls()

                ok = await provider.initialize()
                if ok:
                    self.providers.append(provider)
                    logger.info(f"Provider '{name}' initialized")
                else:
                    logger.warning(f"Provider '{name}' initialization failed")

            except Exception as e:
                logger.error(f"Failed to load provider '{name}': {e}")

        self._initialized = True
        logger.info(f"SearchProviderManager ready — active providers: {[p.name for p in self.providers]}")

    def get_aggregated_tools(self) -> List[Dict[str, Any]]:
        if self.providers:
            return self.providers[0].get_tools()
        return [{
            "type": "function",
            "function": {
                "name": "video_search",
                "description": "Search for videos.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keywords"},
                    },
                    "required": ["query"],
                },
            },
        }]

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

        tasks = [p.search(query, **kwargs) for p in self.providers]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for provider, outcome in zip(self.providers, outcomes):
            if isinstance(outcome, Exception):
                errors.append(f"{provider.name}: {outcome}")
                continue
            if outcome.get("success"):
                all_results.extend(outcome.get("results", []))
                providers_used.append(provider.name)
            else:
                errors.append(f"{provider.name}: {outcome.get('error', 'unknown')}")

        seen_urls = set()
        deduplicated = []
        for v in all_results:
            url = v.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduplicated.append(v)

        return {
            "success": len(deduplicated) > 0 or not errors,
            "results": deduplicated,
            "count": len(deduplicated),
            "providers": providers_used,
            "errors": errors if errors else None,
        }
