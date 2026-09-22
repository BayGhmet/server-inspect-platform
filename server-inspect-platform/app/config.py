"""全局配置。

巡检阈值、数据库位置、调度周期都集中在这里，改配置不用动业务代码。
支持用环境变量覆盖，方便 Docker 里部署时调整。
"""
import os

# SQLite 数据库文件位置
DB_PATH = os.getenv("INSPECT_DB", "data/inspect.db")

# SSH 连接超时（秒）
SSH_CONNECT_TIMEOUT = int(os.getenv("SSH_TIMEOUT", "10"))

# 单条巡检命令的执行超时（秒）
COMMAND_TIMEOUT = int(os.getenv("CMD_TIMEOUT", "30"))

# 定时巡检周期（分钟）。设为 0 表示关闭定时任务。
SCHEDULE_MINUTES = int(os.getenv("SCHEDULE_MINUTES", "0"))

# 巡检阈值。改这里就能调整告警线，不用改检查逻辑。
THRESHOLDS = {
    # 键名          上限    警戒线（达到上限的这个比例即判 WARN）
    "cpu_percent": (80.0, 0.9),
    "mem_percent": (85.0, 0.9),
    "disk_percent": (85.0, 0.9),
    "load_per_core": (1.5, 0.8),
    "ssh_failed_count": (5.0, 0.6),
}
