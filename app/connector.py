"""命令执行器。

对上层暴露统一的 run(command) 接口，屏蔽「命令跑在哪台机器上」的差异：
    LocalConnector —— 本机 shell
    SSHConnector   —— 通过 paramiko 连到远程主机

一次巡检建立一个连接，跑完全部巡检项再关闭（SSH 握手不便宜，不能每条命令连一次）。
"""
from __future__ import annotations

import subprocess

from . import config


class BaseConnector:
    def __init__(self, host):
        self.host = host

    def __enter__(self) -> "BaseConnector":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def run(self, command: str) -> str:
        raise NotImplementedError

    def close(self) -> None:
        """默认什么都不做，本地执行没有连接需要关。"""


class LocalConnector(BaseConnector):
    """在巡检平台自己所在的机器上执行。"""

    def run(self, command: str) -> str:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=config.COMMAND_TIMEOUT,
        )
        # 命令失败时 stdout 可能为空，交给巡检项的判定逻辑处理（判 FAIL 或 WARN）
        return proc.stdout or ""


class SSHConnector(BaseConnector):
    """连到远程主机执行，连接在整个巡检过程中复用。"""

    def __init__(self, host):
        super().__init__(host)
        import paramiko  # 延迟导入：只做本机巡检时不需要这个依赖

        self._client = paramiko.SSHClient()
        # 实验环境里省去 known_hosts 的交互确认
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            hostname=host.address,
            port=host.ssh_port,
            username=host.username,
            password=host.password,
            timeout=config.SSH_CONNECT_TIMEOUT,
            allow_agent=False,
            look_for_keys=False,
        )

    def run(self, command: str) -> str:
        _, stdout, _ = self._client.exec_command(command, timeout=config.COMMAND_TIMEOUT)
        return stdout.read().decode("utf-8", errors="replace")

    def close(self) -> None:
        self._client.close()


def build_connector(host) -> BaseConnector:
    """按主机配置决定走本地还是 SSH。"""
    if host.is_local:
        return LocalConnector(host)
    return SSHConnector(host)
