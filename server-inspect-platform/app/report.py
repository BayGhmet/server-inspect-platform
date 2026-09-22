"""把一次巡检的结果渲染成 Markdown 报告。

报告是给人看的：先给结论（几项正常、几项异常），再按系统/安全分组列明细，
最后把异常项单独拎出来附上说明 —— 面试演示时直接念这段就够。
"""
from __future__ import annotations

from .checks import CHECKS
from .models import Scan

_CATEGORY_OF = {check.key: check.category for check in CHECKS}


def render_markdown(scan: Scan) -> str:
    host = scan.host
    address = "本机" if host.is_local else f"{host.address}:{host.ssh_port}"

    duration = "—"
    if scan.finished_at:
        seconds = (scan.finished_at - scan.started_at).total_seconds()
        duration = f"{seconds:.1f} 秒"

    lines = [
        "# 服务器巡检报告",
        "",
        f"- 主机：{host.name}（{address}）",
        f"- 巡检时间：{scan.started_at:%Y-%m-%d %H:%M:%S}",
        f"- 耗时：{duration}",
        f"- 状态：{_status_label(scan.status)}",
        f"- 结论：共 {scan.total} 项检查，正常 {scan.passed} 项 / 警告 {scan.warned} 项 / 异常 {scan.failed} 项",
        "",
    ]

    if scan.error:
        lines += ["## 巡检中断", "", f"```\n{scan.error}\n```", ""]

    for category in ("系统", "安全"):
        rows = [r for r in scan.results if _CATEGORY_OF.get(r.item_key, "其他") == category]
        if not rows:
            continue
        lines += [
            f"## {category}",
            "",
            "| 检查项 | 实测 | 阈值 | 结果 | 说明 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for r in rows:
            lines.append(
                f"| {r.item_name} | {r.metric_text or '—'} | {r.threshold or '—'} "
                f"| {_status_label(r.status)} | {r.message or '—'} |"
            )
        lines.append("")

    abnormal = [r for r in scan.results if r.status in ("WARN", "FAIL")]
    if abnormal:
        lines += ["## 需要处理的问题", ""]
        for r in abnormal:
            lines.append(f"- **{r.item_name}**（{_status_label(r.status)}）：{r.message}")
        lines.append("")
    else:
        lines += ["## 需要处理的问题", "", "无，本次巡检所有检查项均正常。", ""]

    lines += ["---", "", "由 server-inspect-platform 自动生成。"]
    return "\n".join(lines)


def _status_label(status: str) -> str:
    return {
        "PASS": "正常",
        "WARN": "警告",
        "FAIL": "异常",
        "running": "进行中",
        "success": "已完成",
        "failed": "已中断",
    }.get(status, status)
