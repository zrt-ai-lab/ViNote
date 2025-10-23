"""
API数据模型
定义请求和响应的Pydantic模型
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskResponse(BaseModel):
    """任务创建响应"""
    task_id: str = Field(..., description="任务ID")
    message: str = Field(..., description="提示信息")
    status: TaskStatus = Field(..., description="任务状态")
    progress: int = Field(0, description="进度百分比", ge=0, le=100)


class TaskStatusResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    progress: int = Field(..., description="进度百分比", ge=0, le=100)
    message: Optional[str] = Field(None, description="状态消息")
    result: Optional[Dict[str, Any]] = Field(None, description="任务结果")
    error: Optional[str] = Field(None, description="错误信息")


class VideoPreviewResponse(BaseModel):
    """视频预览响应"""
    success: bool = Field(..., description="是否成功")
    title: Optional[str] = Field(None, description="视频标题")
    duration: Optional[int] = Field(None, description="视频时长（秒）")
    thumbnail: Optional[str] = Field(None, description="缩略图URL")
    description: Optional[str] = Field(None, description="视频描述")
    uploader: Optional[str] = Field(None, description="上传者")
    upload_date: Optional[str] = Field(None, description="上传日期")
    view_count: Optional[int] = Field(None, description="观看次数")
    error: Optional[str] = Field(None, description="错误信息")


class DownloadRequest(BaseModel):
    """视频下载请求"""
    url: str = Field(..., description="视频URL")
    format: str = Field("best", description="下载格式")
    quality: Optional[str] = Field(None, description="视频质量")


class DownloadResponse(BaseModel):
    """视频下载响应"""
    download_id: str = Field(..., description="下载任务ID")
    message: str = Field(..., description="提示信息")
    status: str = Field(..., description="下载状态")


class VideoQARequest(BaseModel):
    """视频问答请求"""
    transcript: str = Field(..., description="视频转录文本")
    question: str = Field(..., description="用户问题")
    language: str = Field("zh", description="回答语言")
