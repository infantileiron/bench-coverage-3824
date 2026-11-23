from datetime import datetime
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(16))


class Segment(Base):
    __tablename__ = 'segments'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    bank: Mapped[str] = mapped_column(String(40))
    stable: Mapped[bool]


class Batch(Base):
    """巡查批次：按实际采集时段（而非回传时间）归集座椅记录。"""
    __tablename__ = 'survey_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(100))
    collected_from: Mapped[datetime] = mapped_column(DateTime)
    collected_to: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 已发起过估算（含补入重算）的次数，同时作为当前派发表版本号
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Capture(Base):
    __tablename__ = 'survey_captures'
    __table_args__ = (
        UniqueConstraint('segment_code', 'campaign', 'round_code', 'asset_code', name='uq_capture_natural'),
        UniqueConstraint('client_ref', name='uq_capture_client_ref'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    segment_code: Mapped[str] = mapped_column(ForeignKey('segments.code'))
    campaign: Mapped[str] = mapped_column(String(32), index=True)
    round_code: Mapped[str] = mapped_column(String(1))
    asset_code: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(12))
    # 设备/整批重送去重键：同一来源记录只入库一次
    client_ref: Mapped[str] = mapped_column(String(80))
    # 实际采集时间与回传时间，用于判定迟到补入
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # current 当批台账 / pending 补入队列 / supplemented 已补入
    intake_state: Mapped[str] = mapped_column(String(12), default='current', index=True)


class Analysis(Base):
    __tablename__ = 'coverage_plans'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), index=True)
    parameters: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # 版本管理：同一批次的派发表版本链
    campaign: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_effective: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    trigger: Mapped[str] = mapped_column(String(12), default='initial')  # initial / supplement
    # 触发本次重算的补入记录 id 列表
    supplement_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 与上一有效版本的漏查对比与差异记录，计算成功后一次性写入
    diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Audit(Base):
    __tablename__ = 'audits'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(100))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
