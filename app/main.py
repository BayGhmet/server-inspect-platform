"""FastAPI 应用入口：REST 接口 + 定时巡检 + 一个极简页面。

启动后：
    页面     http://127.0.0.1:8000/
    接口文档  http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import __version__, config
from .database import SessionLocal, get_db, init_db
from .models import Host, Scan
from .report import render_markdown
from .runner import run_scan
from .schemas import HostCreate, HostOut, ScanCreate, ScanDetailOut, ScanOut

scheduler = BackgroundScheduler()


def _scheduled_scan() -> None:
    """定时任务：把登记过的每台主机都巡检一遍。"""
    db = SessionLocal()
    try:
        for host in db.query(Host).all():
            run_scan(db, host)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if config.SCHEDULE_MINUTES > 0:
        scheduler.add_job(_scheduled_scan, "interval", minutes=config.SCHEDULE_MINUTES)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="服务器巡检平台",
    description=(
        "对 Linux 主机执行系统与安全两类巡检，结果写入数据库并生成 Markdown 报告。\n\n"
        "本机巡检取 address=local，远程巡检填 IP + SSH 账号。"
    ),
    version=__version__,
    lifespan=lifespan,
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# --------------------------- 页面 ---------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db)):
    hosts = db.query(Host).order_by(Host.id).all()
    scans = db.query(Scan).order_by(Scan.id.desc()).limit(10).all()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "hosts": hosts, "scans": scans},
    )


# --------------------------- 主机管理 ---------------------------
@app.post("/api/hosts", response_model=HostOut, status_code=201, tags=["主机"])
def create_host(payload: HostCreate, db: Session = Depends(get_db)):
    """登记一台被巡检的主机。address 填 local 表示平台自己所在的机器。"""
    host = Host(**payload.model_dump())
    db.add(host)
    db.commit()
    db.refresh(host)
    return host


@app.get("/api/hosts", response_model=list[HostOut], tags=["主机"])
def list_hosts(db: Session = Depends(get_db)):
    return db.query(Host).order_by(Host.id).all()


@app.delete("/api/hosts/{host_id}", status_code=204, tags=["主机"])
def delete_host(host_id: int, db: Session = Depends(get_db)):
    host = db.get(Host, host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="主机不存在")
    db.delete(host)
    db.commit()


# --------------------------- 巡检 ---------------------------
@app.post("/api/scans", response_model=ScanDetailOut, status_code=201, tags=["巡检"])
def create_scan(payload: ScanCreate, db: Session = Depends(get_db)):
    """对指定主机发起一次巡检，同步等待结果返回。"""
    host = db.get(Host, payload.host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="主机不存在")
    scan = run_scan(db, host)
    db.refresh(scan)
    return scan


@app.get("/api/scans", response_model=list[ScanOut], tags=["巡检"])
def list_scans(
    host_id: int | None = Query(None, description="只看某台主机的记录"),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """查历史巡检记录，按时间倒序。"""
    query = db.query(Scan)
    if host_id is not None:
        query = query.filter(Scan.host_id == host_id)
    return query.order_by(Scan.id.desc()).limit(limit).all()


@app.get("/api/scans/{scan_id}", response_model=ScanDetailOut, tags=["巡检"])
def get_scan(scan_id: int, db: Session = Depends(get_db)):
    """查某次巡检的逐项结果。"""
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="巡检记录不存在")
    return scan


@app.get("/api/scans/{scan_id}/report", response_class=PlainTextResponse, tags=["巡检"])
def get_report(scan_id: int, db: Session = Depends(get_db)):
    """导出 Markdown 巡检报告。"""
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="巡检记录不存在")
    return PlainTextResponse(render_markdown(scan), media_type="text/markdown; charset=utf-8")


# --------------------------- 健康检查 ---------------------------
@app.get("/api/health", tags=["其他"])
def health():
    return {"status": "ok", "version": __version__}
