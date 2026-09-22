"""巡检执行引擎：连上目标主机 → 逐项跑检查 → 结果落库 → 汇总。

刻意不做异步/并发：一次巡检 7 条命令，串行也就几秒，
先保证逻辑清晰和结果可追溯，并发留到二期（多主机时才有必要）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .checks import CHECKS, Check
from .connector import BaseConnector, build_connector
from .models import CheckResult, Host, Scan


def run_scan(db: Session, host: Host) -> Scan:
    """对一台主机执行一次完整巡检，返回已落库的 Scan 记录。"""
    scan = Scan(host_id=host.id, started_at=datetime.now(), status="running")
    db.add(scan)
    db.commit()
    db.refresh(scan)

    try:
        with build_connector(host) as conn:
            for check in CHECKS:
                value, status, message = _run_one(conn, check)
                db.add(
                    CheckResult(
                        scan_id=scan.id,
                        item_key=check.key,
                        item_name=check.name,
                        metric_value=value,
                        metric_text=_format_value(value),
                        threshold=check.threshold,
                        status=status,
                        message=message,
                    )
                )
        scan.status = "success"
    except Exception as exc:  # 连不上主机、命令超时等
        scan.status = "failed"
        scan.error = f"{type(exc).__name__}: {exc}"

    db.commit()
    _summarize(db, scan)
    return scan


def _run_one(conn: BaseConnector, check: Check) -> tuple[float | None, str, str]:
    """跑一条巡检命令并判定。命令本身出错不中断整次巡检。"""
    try:
        output = conn.run(check.command)
    except Exception as exc:
        return None, "FAIL", f"命令执行失败：{type(exc).__name__}"
    return check.evaluate(output)


def _format_value(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _summarize(db: Session, scan: Scan) -> None:
    """把逐项结果汇总成 total / passed / warned / failed 四个数字。"""
    results = db.query(CheckResult).filter(CheckResult.scan_id == scan.id).all()
    scan.total = len(results)
    scan.passed = sum(1 for r in results if r.status == "PASS")
    scan.warned = sum(1 for r in results if r.status == "WARN")
    scan.failed = sum(1 for r in results if r.status == "FAIL")
    scan.finished_at = datetime.now()
    db.commit()
