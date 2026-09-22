"""数据模型：hosts（主机） → scans（一次巡检） → check_results（逐项结果）。"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Host(Base):
    """一台被巡检的主机。address 为 local 时表示平台自己所在的机器。"""

    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    address: Mapped[str] = mapped_column(String(128), default="local")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    username: Mapped[str] = mapped_column(String(64), default="")
    password: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    scans = relationship("Scan", back_populates="host", cascade="all, delete-orphan")

    @property
    def is_local(self) -> bool:
        return self.address in ("", "local", "127.0.0.1", "localhost")


class Scan(Base):
    """一次巡检记录。total/passed/warned/failed 是汇总数字，列表页直接读这几个字段。"""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/success/failed
    error: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    warned: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)

    host = relationship("Host", back_populates="scans")
    results = relationship("CheckResult", back_populates="scan", cascade="all, delete-orphan")


class CheckResult(Base):
    """单个巡检项的结论。

    metric_value 是采集到的实际值，threshold 是判定阈值（文字描述），
    status 取 PASS / WARN / FAIL，message 里带上人话解释。
    """

    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"))
    item_key: Mapped[str] = mapped_column(String(64))
    item_name: Mapped[str] = mapped_column(String(64))
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_text: Mapped[str] = mapped_column(String(64), default="")
    threshold: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="PASS")
    message: Mapped[str] = mapped_column(Text, default="")

    scan = relationship("Scan", back_populates="results")
