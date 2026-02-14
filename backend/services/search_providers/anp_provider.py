import logging
from pathlib import Path
from typing import Any, Dict, List

from backend.services.search_providers.base import SearchProvider

logger = logging.getLogger(__name__)

try:
    from anp.anp_crawler import ANPCrawler
    ANP_AVAILABLE = True
except ImportError:
    ANP_AVAILABLE = False
    logger.warning("ANP library not installed — ANPSearchProvider disabled")


class ANPSearchProvider(SearchProvider):

    name = "anp"

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.crawler = None
        self.openai_tools: List[Dict] = []

    def is_available(self) -> bool:
        return ANP_AVAILABLE

    async def initialize(self) -> bool:
        if not ANP_AVAILABLE:
            return False

        try:
            anp_dir = Path(__file__).parent.parent.parent / "anp"
            did_path = anp_dir / "client_did_keys" / "did.json"
            key_path = anp_dir / "client_did_keys" / "key-1_private.pem"

            if not did_path.exists() or not key_path.exists():
                logger.error(f"DID key files missing: {did_path}")
                return False

            self.crawler = ANPCrawler(
                did_document_path=str(did_path),
                private_key_path=str(key_path),
                cache_enabled=True,
            )

            _content, interfaces = await self.crawler.fetch_text(self.server_url)
            self.openai_tools = interfaces
            logger.info(f"ANP initialized — {len(interfaces)} tools discovered at {self.server_url}")
            return True

        except Exception as e:
            logger.error(f"ANP initialization failed: {e}")
            return False

    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        if not self.crawler:
            return {"success": False, "error": "ANP not initialized", "results": [], "count": 0, "provider": self.name}

        try:
            tool_args = {"query": query, **kwargs}
            result = await self.crawler.execute_tool_call(tool_name="video_search", arguments=tool_args)

            if result.get("success"):
                data = result.get("result", {})
                videos = []
                for item in data.get("results", []):
                    videos.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "cover": item.get("cover", ""),
                        "thumbnail": item.get("thumbnail", ""),
                        "description": item.get("description", ""),
                        "platform": item.get("platform", "unknown"),
                        "duration": item.get("duration", ""),
                        "author": item.get("author", ""),
                        "play": item.get("play", 0),
                        "views": item.get("views", 0),
                    })
                return {
                    "success": True,
                    "results": videos,
                    "count": len(videos),
                    "provider": self.name,
                }

            return {
                "success": False,
                "error": result.get("error", "Unknown ANP error"),
                "results": [],
                "count": 0,
                "provider": self.name,
            }

        except Exception as e:
            logger.error(f"ANP search failed: {e}")
            return {"success": False, "error": str(e), "results": [], "count": 0, "provider": self.name}

    def get_tools(self) -> List[Dict[str, Any]]:
        return list(self.openai_tools)
