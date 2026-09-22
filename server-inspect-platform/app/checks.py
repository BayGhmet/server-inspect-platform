"""巡检项定义。

每一项 = 一条在目标机器上执行的 shell 命令 + 一段从输出里取值并判定的逻辑。

本地巡检和 SSH 远程巡检共用同一份定义 —— 区别只在于命令在哪台机器上跑，
所以巡检项只关心「跑什么命令」「怎么判」，不关心「在哪跑」。

判定结果分三档：
    PASS  正常
    WARN  接近阈值，或指标不可用（例如日志文件读不到）
    FAIL  越过阈值

════════════════════════════════════════════════════════════════════
所有命令一律以 `LC_ALL=C` 开头，这是硬性要求，不是风格问题。
────────────────────────────────────────────────────────────────────
解析命令输出时必须固定 locale：

  · 中文环境下 `free` 的表头会被翻译成「内存：」而不是 `Mem:`，
    用 `/^Mem:/` 匹配会一条都取不到 → 数值解析为空 → 该项永远报 FAIL。
  · 小数点是另一个雷：某些 locale 用逗号作小数点（`39,47`），
    会被 `_first_number` 当成两个数字拆开，算出静默错误的数值。

`free` 的 Mem 行固定在**第 2 行**，所以取 `NR==2` 比匹配表头更稳 ——
既不怕翻译，也不怕表头排版变化。
════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import config

# evaluate 的返回值：(指标数值 or None, 状态, 人话说明)
EvaluateResult = tuple[float | None, str, str]


@dataclass(frozen=True)
class Check:
    key: str
    name: str
    category: str  # 系统 / 安全
    command: str
    threshold: str  # 给人看的阈值说明
    evaluate: Callable[[str], EvaluateResult]


def _first_number(text: str) -> float | None:
    """从命令输出里取第一个数字（顺带去掉百分号、冒号、千分位逗号）。"""
    cleaned = text.replace("%", " ").replace(":", " ").replace(",", " ")
    for token in cleaned.split():
        try:
            return float(token)
        except ValueError:
            continue
    return None


def _numeric_check(
    *,
    key: str,
    name: str,
    category: str,
    command: str,
    unit: str,
    threshold_text: str,
    unavailable_hint: str = "指标不可用（可能是权限不足或命令缺失）",
) -> Check:
    """阈值型巡检项的工厂：从输出取第一个数字，和配置里的上限比较。"""
    limit, warn_ratio = config.THRESHOLDS[key]

    def evaluate(output: str) -> EvaluateResult:
        value = _first_number(output)
        if value is None:
            return None, "FAIL", "无法从命令输出中解析出数值，命令可能执行失败"
        if value < 0:
            return value, "WARN", unavailable_hint
        if value >= limit:
            status = "FAIL"
        elif value >= limit * warn_ratio:
            status = "WARN"
        else:
            status = "PASS"
        return value, status, f"实测 {value:.1f}{unit}，阈值 {limit:g}{unit}"

    return Check(key, name, category, command, threshold_text, evaluate)


def _evaluate_load(output: str) -> EvaluateResult:
    """系统负载：输出形如「0.42 4」，取 1 分钟负载 ÷ 核数，得到每核负载。"""
    tokens = [t for t in output.replace(",", " ").split() if t.replace(".", "").isdigit()]
    if len(tokens) < 2:
        return None, "FAIL", "无法解析负载值（应输出「1 分钟负载 核数」两个数字）"
    load1, cores = float(tokens[0]), float(tokens[1])
    if cores <= 0:
        return None, "FAIL", "核数解析异常"
    per_core = load1 / cores
    limit, warn_ratio = config.THRESHOLDS["load_per_core"]
    if per_core >= limit:
        status = "FAIL"
    elif per_core >= limit * warn_ratio:
        status = "WARN"
    else:
        status = "PASS"
    return per_core, status, f"负载 {load1:.2f} / {cores:.0f} 核 = {per_core:.2f}，阈值 {limit:g}"


def _evaluate_root_login(output: str) -> EvaluateResult:
    """基线：sshd_config 里的 PermitRootLogin。"""
    line = output.strip().lower()
    if not line:
        return None, "WARN", "sshd_config 未显式配置 PermitRootLogin，当前依赖系统默认值"
    value = line.split()[-1]
    if value == "no":
        return None, "PASS", "已禁止 root 直接登录（PermitRootLogin no）"
    if value in ("prohibit-password", "without-password"):
        return None, "PASS", "root 仅允许密钥登录，不允许密码登录"
    if value == "yes":
        return None, "FAIL", "允许 root 直接登录，存在暴力破解风险，建议改为 no"
    return None, "WARN", f"无法识别的配置值：{value}"


def _evaluate_pass_max_days(output: str) -> EvaluateResult:
    """基线：密码最长有效期（CIS 建议不超过 365 天）。"""
    value = _first_number(output)
    if value is None:
        return None, "WARN", "未找到 PASS_MAX_DAYS 配置"
    if value >= 99999:
        return value, "FAIL", "密码永不过期（PASS_MAX_DAYS=99999），不符合合规要求"
    if value > 365:
        return value, "FAIL", f"密码最长有效期 {value:.0f} 天，超过 365 天"
    if value > 180:
        return value, "WARN", f"密码最长有效期 {value:.0f} 天，建议收紧到 180 天以内"
    return value, "PASS", f"密码最长有效期 {value:.0f} 天"


CHECKS: list[Check] = [
    # ---------- 系统层 ----------
    _numeric_check(
        key="cpu_percent",
        name="CPU 使用率",
        category="系统",
        # vmstat 第 2 个采样才是「最近 1 秒」的真实值，第 1 个是开机至今均值
        command="LC_ALL=C vmstat 1 2 | tail -1 | awk '{print 100-$15}'",
        unit="%",
        threshold_text="< 80%",
    ),
    _numeric_check(
        key="mem_percent",
        name="内存使用率",
        category="系统",
        # 取第 2 行而不是匹配表头：中文 locale 下表头是「内存：」，匹配 Mem: 会取空
        command="LC_ALL=C free | awk 'NR==2 {print $3/$2*100}'",
        unit="%",
        threshold_text="< 85%",
    ),
    _numeric_check(
        key="disk_percent",
        name="根分区磁盘使用率",
        category="系统",
        # -P 强制 POSIX 单行输出，防止设备名过长时 df 折行导致 NR==2 取错
        command="LC_ALL=C df -P / | awk 'NR==2 {print $5}' | tr -d '%'",
        unit="%",
        threshold_text="< 85%",
    ),
    Check(
        key="load_per_core",
        name="系统负载（每核）",
        category="系统",
        command="echo $(LC_ALL=C awk '{print $1}' /proc/loadavg) $(nproc)",
        threshold="< 1.5",
        evaluate=_evaluate_load,
    ),
    # ---------- 安全层 ----------
    _numeric_check(
        key="ssh_failed_count",
        name="SSH 登录失败次数",
        category="安全",
        command=(
            "if [ -r /var/log/auth.log ]; then "
            "LC_ALL=C awk '/Failed password/ {n++} END {print n+0}' /var/log/auth.log; "
            "else echo -1; fi"
        ),
        unit=" 次",
        # 注意是「达到即告警」：阈值 5 表示 5 次就算异常，与 ssh_audit.sh 的 -ge 语义一致
        threshold_text="≥ 5 次即告警",
        unavailable_hint="读不到 /var/log/auth.log，需要 root 权限或加入 adm 组",
    ),
    Check(
        key="permit_root_login",
        name="SSH root 登录策略",
        category="安全",
        command="LC_ALL=C grep -iE '^[[:space:]]*PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null | tail -1",
        threshold="不允许 root 直接登录",
        evaluate=_evaluate_root_login,
    ),
    Check(
        key="pass_max_days",
        name="密码有效期策略",
        category="安全",
        command="LC_ALL=C grep -E '^[[:space:]]*PASS_MAX_DAYS' /etc/login.defs 2>/dev/null | awk '{print $2}'",
        threshold="≤ 365 天",
        evaluate=_evaluate_pass_max_days,
    ),
]


def grouped_checks() -> dict[str, list[Check]]:
    """按「系统 / 安全」分组返回，报告和页面按组展示。"""
    groups: dict[str, list[Check]] = {}
    for check in CHECKS:
        groups.setdefault(check.category, []).append(check)
    return groups
