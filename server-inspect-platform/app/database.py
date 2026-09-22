"""数据库连接与会话管理（SQLAlchemy 2.x + SQLite）。"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

# 确保数据库所在目录存在（SQLite 不会自动建目录）
_db_dir = os.path.dirname(config.DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

DATABASE_URL = f"sqlite:///{config.DB_PATH}"

# check_same_thread=False：SQLite 默认禁止跨线程复用连接，
# 而 FastAPI 的同步视图跑在线程池里，定时任务也在另一个线程，所以必须关掉这个限制。
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def get_db():
    """FastAPI 依赖注入用的会话工厂：请求进来开一个，请求结束关掉。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（已存在则跳过）。"""
    from . import models  # noqa: F401  导入才会注册模型

    Base.metadata.create_all(bind=engine)
