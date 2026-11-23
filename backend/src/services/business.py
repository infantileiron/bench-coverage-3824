from datetime import datetime, timezone

from fastapi import HTTPException
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.config.settings import REDIS_URL
from src.constants.enums import IntakeState, Status
from src.models.entities import Analysis, Audit, Batch, Segment, Capture

queue = Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
QUEUE = 'bench-coverage:notifications'
SURVEY_TIMESTAMPS = {'collected_from', 'collected_to', 'closed_at', 'collected_at', 'received_at'}


def utc_for_storage(value):
    """MySQL DATETIME stores UTC without an offset. Legacy offset-free input already uses UTC."""
    if value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def record(obj, exclude=()):
    values = {col.key: getattr(obj, col.key) for col in obj.__table__.columns if col.key not in exclude}
    for key in SURVEY_TIMESTAMPS & values.keys():
        if values[key] is not None:
            values[key] = values[key].replace(tzinfo=timezone.utc)
    return values


def snapshot_record(obj):
    """JSON 列专用：datetime 转 ISO 字符串，保证快照可序列化且口径可复现。"""
    return {key: (value.isoformat() if isinstance(value, datetime) else value)
            for key, value in record(obj).items()}


def audit(db, user, action, subject):
    db.add(Audit(user_id=user.id, action=action, subject=str(subject)))


def save_segment(db, data, user):
    if db.scalar(select(Segment.id).where(Segment.code == data.code)):
        raise HTTPException(409, '区段编号已经登记')
    item = Segment(**data.model_dump())
    db.add(item)
    audit(db, user, 'create', data.code)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '区段编号已经登记') from exc
    return record(item)


def create_batch(db, data, user):
    collected_from = utc_for_storage(data.collected_from)
    collected_to = utc_for_storage(data.collected_to)
    if collected_to <= collected_from:
        raise HTTPException(422, '采集结束时间必须晚于开始时间')
    item = Batch(campaign=data.campaign, title=data.title,
                 collected_from=collected_from, collected_to=collected_to,
                 closed_at=collected_to, version=0)
    db.add(item)
    audit(db, user, 'create_batch', data.campaign)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '该巡查批次已经建立') from exc
    return record(item)


def list_batches(db):
    batches = db.scalars(select(Batch).order_by(Batch.collected_from.desc()))
    result = []
    for batch in batches:
        info = record(batch)
        info['pending_count'] = db.scalar(select(func.count()).select_from(Capture).where(
            Capture.campaign == batch.campaign,
            Capture.intake_state == IntakeState.PENDING))
        info['supplemented_count'] = db.scalar(select(func.count()).select_from(Capture).where(
            Capture.campaign == batch.campaign,
            Capture.intake_state == IntakeState.SUPPLEMENTED))
        result.append(info)
    return result


def _get_batch(db, campaign):
    batch = db.scalar(select(Batch).where(Batch.campaign == campaign))
    if not batch:
        raise HTTPException(422, '该巡查批次尚未建立采集时段，请先登记批次')
    return batch


def save_capture(db, data, user):
    if not db.scalar(select(Segment.id).where(Segment.code == data.segment_code)):
        raise HTTPException(422, '请选择有效区段')
    batch = _get_batch(db, data.campaign)
    # 幂等预检：设备重试或整批重送保持同一 client_ref，直接返回已入库记录
    existing = db.scalar(select(Capture).where(Capture.client_ref == data.client_ref))
    if existing:
        return record(existing)
    # 自然键预检：同区段/批次/轮次/标签已由不同来源记录登记
    duplicate = db.scalar(select(Capture).where(
        Capture.segment_code == data.segment_code,
        Capture.campaign == data.campaign,
        Capture.round_code == data.round_code,
        Capture.asset_code == data.asset_code))
    if duplicate:
        raise HTTPException(409, '该轮资产标签已经登记，且来自不同来源记录')
    collected_at = utc_for_storage(data.collected_at) if data.collected_at else batch.collected_to
    # 同一批次按实际采集时段归集：落在窗口内即当批，跨日迟到进入补入队列
    if batch.collected_from <= collected_at <= batch.collected_to:
        intake_state = IntakeState.CURRENT
    else:
        intake_state = IntakeState.PENDING
    item = Capture(segment_code=data.segment_code, campaign=data.campaign,
                   round_code=data.round_code, asset_code=data.asset_code, state=data.state,
                   client_ref=data.client_ref, collected_at=collected_at,
                   intake_state=intake_state)
    db.add(item)
    key = f'{data.segment_code}/{data.campaign}/{data.round_code}/{data.asset_code}'
    audit(db, user, 'capture_late' if intake_state == IntakeState.PENDING else 'capture', key)
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发兜底：预检后仍可能撞唯一约束，绝不重复入库
        db.rollback()
        raced = db.scalar(select(Capture).where(Capture.client_ref == data.client_ref))
        if raced:
            return record(raced)
        raise HTTPException(409, '该轮资产标签已经登记，且来自不同来源记录') from exc
    return record(item)


def supplement_queue(db, campaign):
    """补入队列：窗口关闭后回传、尚未进入任何派发表版本的记录。"""
    _get_batch(db, campaign)
    rows = db.scalars(select(Capture).where(
        Capture.campaign == campaign,
        Capture.intake_state == IntakeState.PENDING).order_by(Capture.received_at, Capture.id))
    return [record(row) for row in rows]


def verify_capture(db, id, user):
    row = db.scalar(select(Capture).where(Capture.id == id).with_for_update())
    if row is None:
        raise HTTPException(404, '找不到待核标签')
    if row.state != 'verified':
        row.state = 'verified'
        audit(db, user, 'verify_capture', f'{row.segment_code}/{row.asset_code}')
        db.commit()
    return record(row)


def _effective_analyses(db, campaign):
    return db.scalars(select(Analysis).where(
        Analysis.campaign == campaign, Analysis.is_effective.is_(True)).order_by(Analysis.id)).all()


def submit(db, data, user):
    batch = _get_batch(db, data.campaign)
    segments = [record(row) for row in db.scalars(select(Segment).order_by(Segment.code))]
    if not segments:
        raise HTTPException(422, '请先登记巡查区段')
    # 初始估算仅锁定窗口内台账记录；迟到记录留在补入队列，不污染当批口径
    evidence = db.scalars(select(Capture).where(
        Capture.campaign == data.campaign,
        Capture.intake_state == IntakeState.CURRENT).order_by(Capture.id))
    snapshot = [snapshot_record(row) for row in evidence]
    if not snapshot:
        raise HTTPException(422, '该巡查批次的采集窗口内还没有记录')
    if _effective_analyses(db, data.campaign):
        raise HTTPException(409, '该批次已生成派发表；补入记录请使用补入重算，旧版会保留原口径')
    parameters = {**data.model_dump(exclude={'title'}), 'segments': segments}
    batch.version += 1
    item = Analysis(title=data.title, status=Status.QUEUED, parameters=parameters,
                    snapshot=snapshot, author_id=user.id, result=None,
                    campaign=data.campaign, version=batch.version, is_effective=True,
                    trigger='initial', supplement_ids=[])
    db.add(item)
    db.flush()
    audit(db, user, 'queue', item.id)
    db.commit()
    _notify(item.id)
    return record(item, ('snapshot',))


def recalc_with_supplements(db, campaign, user):
    """对补入队列发起一次性重算：成功后原子切换有效版本，失败保留旧版。"""
    batch = _get_batch(db, campaign)
    pending = db.scalars(select(Capture).where(
        Capture.campaign == campaign,
        Capture.intake_state == IntakeState.PENDING).order_by(Capture.id)).all()
    if not pending:
        raise HTTPException(422, '补入队列没有待处理记录')
    prior_versions = _effective_analyses(db, campaign)
    if not prior_versions:
        raise HTTPException(409, '该批次尚未生成首版派发表，无法补入重算')
    latest = prior_versions[-1]
    if latest.status in (Status.QUEUED, Status.RUNNING):
        raise HTTPException(409, '该批次已有估算任务在处理中，请等待完成')
    # 快照 = 旧版口径 + 全部补入记录；待核标签按既有规则在计算中排除
    supplemented_ids = [row.id for row in pending]
    snapshot = list(latest.snapshot) + [snapshot_record(row) for row in pending]
    parameters = dict(latest.parameters)
    batch.version += 1
    item = Analysis(title=latest.title, status=Status.QUEUED, parameters=parameters,
                    snapshot=snapshot, author_id=user.id, result=None,
                    campaign=campaign, version=batch.version, is_effective=False,
                    trigger='supplement', supplement_ids=supplemented_ids)
    db.add(item)
    db.flush()
    # 记录被锁定为“补入中”，重复点击或并发重算不会再次纳入
    for row in pending:
        row.intake_state = IntakeState.SUPPLEMENTED
    audit(db, user, 'supplement_recalc', f'{campaign}#{item.id}')
    db.commit()
    _notify(item.id)
    return record(item, ('snapshot',))


def _notify(analysis_id):
    try:
        queue.lpush(QUEUE, analysis_id)
    except RedisError:
        pass


def get_analysis(db, id):
    item = db.get(Analysis, id)
    if not item:
        raise HTTPException(404, '找不到补巡单')
    return item


def publish(db, id, note, user):
    item = db.scalar(select(Analysis).where(Analysis.id == id).with_for_update())
    if not item:
        raise HTTPException(404, '找不到补巡单')
    if item.status != Status.COMPLETED:
        raise HTTPException(409, '只有已完成的补巡单可签核')
    if not item.is_effective:
        raise HTTPException(409, '该版本已被新版替代，不是当前有效版本')
    item.status = Status.PUBLISHED
    item.note = note
    audit(db, user, 'publish', id)
    db.commit()
    return record(item, ('snapshot',))
