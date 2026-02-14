from abc import ABC, abstractmethod
from typing import Any, Dict, List


class SearchProvider(ABC):
    """搜索源抽象基类。所有搜索协议（ANP / Local / A2A / ...）实现此接口。"""

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

    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """返回 OpenAI function-calling tools 格式的工具定义列表。"""
        ...

    def is_available(self) -> bool:
        """检查此 provider 是否可用（依赖已安装、认证已完成等）。"""
        return True
