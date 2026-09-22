"""接口的请求体与响应体定义（Pydantic）。"""
from datetime import datetime

from pydantic import BaseModel, Field


class HostCreate(BaseModel):
    """新增主机的请求体。address 留空或填 local 表示巡检平台自己。"""

    name: str = Field(..., min_length=1, max_length=64, description="主机别名")
    address: str = Field("local", max_length=128, description="IP 或域名；local 表示本机")
    ssh_port: int = Field(22, ge=1, le=65535)
    username: str = Field("", max_length=64)
    password: str = Field("", max_length=128)


class ScanCreate(BaseModel):
    """发起一次巡检的请求体。"""

    host_id: int = Field(..., description="要巡检的主机 ID")


class HostOut(BaseModel):
    id: int
    name: str
    address: str
    ssh_port: int
    username: str
    is_local: bool = False

    model_config = {"from_attributes": True}


class CheckResultOut(BaseModel):
    item_key: str
    item_name: str
    metric_value: float | None
    metric_text: str
    threshold: str
    status: str
    message: str

    model_config = {"from_attributes": True}


class ScanOut(BaseModel):
    """巡检记录的汇总信息。"""

    id: int
    host_id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    total: int
    passed: int
    warned: int
    failed: int

    model_config = {"from_attributes": True}


class ScanDetailOut(ScanOut):
    """巡检详情：汇总 + 逐项结果。"""

    error: str = ""
    results: list[CheckResultOut] = []
