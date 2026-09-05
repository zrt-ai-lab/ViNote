from abc import ABC, abstractmethod
from typing import Any, Dict


class SearchProvider(ABC):
    """视频搜索接口，统一业务搜索结果。工具描述由 Agent 运行时持有。"""

    name: str = "unknown"

    @abstractmethod
    async def initialize(self) -> bool:
        """初始化连接/认证。返回是否成功。"""
        ...

    @abstractmethod
    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        执行搜索。

        Returns:
            {"success": bool, "results": [...], "count": int, "provider": self.name}
        """
        ...
