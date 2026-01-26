"""API响应类"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ApiResponse:
    """统一的API响应类

    Attributes:
        success: 操作是否成功
        message: 响应消息
        data: 响应数据(可选)
    """

    success: bool
    message: str
    data: Any | None = None

    def __bool__(self) -> bool:
        """支持布尔判断，返回success状态"""
        return self.success

    @classmethod
    def ok(cls, message: str = "操作成功", data: Any | None = None) -> "ApiResponse":
        """创建成功响应

        Args:
            message: 成功消息
            data: 响应数据

        Returns:
            ApiResponse: 成功响应对象
        """
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, data: Any | None = None) -> "ApiResponse":
        """创建失败响应

        Args:
            message: 错误消息
            data: 响应数据

        Returns:
            ApiResponse: 失败响应对象
        """
        return cls(success=False, message=message, data=data)
