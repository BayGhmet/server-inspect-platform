#!/usr/bin/env bash
# 一键启动（开发模式，代码改动自动重载）
#
# 用法：
#   bash start.sh
#
# 首次运行会自动建虚拟环境、装依赖，然后启动服务。
# 虚拟环境半途坏掉（缺 bin/activate）会自动清除重建，不用手动删。

set -e
cd "$(dirname "$0")"

VENV=.venv

# 国内直连 PyPI 很慢，默认走清华镜像；想换源就设置 PIP_INDEX 环境变量
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# --- 判断虚拟环境是否可用 -------------------------------------------------
# 只看目录存不存在是不够的：上一次创建中途失败会留下一个空壳目录，
# 那种情况下必须删掉重建，否则后面会报「.venv/bin/activate: 没有那个文件」。
need_venv=0
if [ ! -d "$VENV" ]; then
  need_venv=1
elif [ ! -f "$VENV/bin/activate" ]; then
  echo "==> 检测到损坏的虚拟环境（缺少 $VENV/bin/activate），正在清除后重建"
  rm -rf "$VENV"
  need_venv=1
fi

if [ "$need_venv" = 1 ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] 找不到 python3，请先安装：sudo apt install -y python3" >&2
    exit 1
  fi

  echo "==> 创建虚拟环境"
  if ! python3 -m venv "$VENV"; then
    echo "" >&2
    echo "[!] 创建虚拟环境失败（多半是系统缺 venv 模块）。先装这两个包再重试：" >&2
    echo "    sudo apt update && sudo apt install -y python3-venv python3-pip" >&2
    exit 1
  fi
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

# --- 安装依赖 -------------------------------------------------------------
echo "==> 安装依赖（源：$PIP_INDEX）"
if ! pip install -q -i "$PIP_INDEX" -r requirements.txt; then
  echo "" >&2
  echo "[!] 依赖安装失败。如果卡在下载，先确认虚拟机能不能上网：" >&2
  echo "    ping -c 2 pypi.tuna.tsinghua.edu.cn" >&2
  echo "    能上网就换回官方源再试：PIP_INDEX=https://pypi.org/simple bash start.sh" >&2
  exit 1
fi

if ! python -c 'import fastapi, uvicorn' 2>/dev/null; then
  echo "[!] 依赖装完了但 import 失败，请把上面完整输出发我" >&2
  exit 1
fi

echo ""
echo "==> 服务已就绪"
echo "    页面      http://127.0.0.1:8000"
echo "    接口文档  http://127.0.0.1:8000/docs"
echo ""
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
