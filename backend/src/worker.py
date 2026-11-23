import json
import logging
import time
from pathlib import Path

from redis.exceptions import RedisError
from sqlalchemy import select, update

from src.config.database import Session
from src.constants.enums import IntakeState, Status
from src.models.entities import Analysis, Capture
from src.services.business import QUEUE, queue, record
from src.services.coverage import analyze, build_diff

ARTIFACT_DIR = Path('/artifacts')


def _write_artifact(analysis_id, result):
    # 先写临时文件再原子替换，避免下载到半成品
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    temp = ARTIFACT_DIR / f'.segment-{analysis_id}.tmp'
    temp.write_text(json.dumps(result, ensure_ascii=False))
    temp.replace(ARTIFACT_DIR / f'segment-{analysis_id}.json')


def _run_job(item, db):
    result = analyze(item.snapshot, item.parameters)
    if item.trigger == 'supplement':
        previous = db.scalar(select(Analysis).where(
            Analysis.campaign == item.campaign,
            Analysis.is_effective.is_(True),
            Analysis.id != item.id).order_by(Analysis.version.desc()))
        supplement_rows = db.scalars(select(Capture).where(
            Capture.id.in_(item.supplement_ids or []))).all()
        item.diff = build_diff(previous.result if previous else None, result,
                               [record(row) for row in supplement_rows])
    _write_artifact(item.id, result)
    item.result = result
    item.status = Status.COMPLETED
    if item.trigger == 'supplement':
        # 一次性原子切换：旧版整体置为失效，新版成为唯一有效版本
        db.execute(update(Analysis).where(
            Analysis.campaign == item.campaign,
            Analysis.is_effective.is_(True),
            Analysis.id != item.id).values(is_effective=False))
        item.is_effective = True


def next_job():
    with Session() as db:
        item = db.scalar(select(Analysis).where(Analysis.status == Status.QUEUED)
                         .order_by(Analysis.id).limit(1).with_for_update(skip_locked=True))
        if not item:
            return False
        item.status = Status.RUNNING
        db.commit()
        try:
            with db.begin():
                _run_job(item, db)
        except ValueError as exc:
            db.rollback()
            item.note = str(exc)
            item.status = Status.FAILED
            _release_supplements(db, item)
            db.commit()
        except Exception:
            logging.exception('Analysis %s failed', item.id)
            db.rollback()
            item.note = '后台计算失败，请检查数据后重提'
            item.status = Status.FAILED
            _release_supplements(db, item)
            db.commit()
        return True


def _release_supplements(db, item):
    """重算失败：补入记录退回队列，旧派发表保持有效与原口径。"""
    if item.trigger != 'supplement' or not item.supplement_ids:
        return
    db.execute(update(Capture).where(Capture.id.in_(item.supplement_ids))
               .values(intake_state=IntakeState.PENDING))
    item.is_effective = False


def main():
    with Session() as db:
        db.execute(update(Analysis).where(Analysis.status == Status.RUNNING).values(status=Status.QUEUED))
        db.commit()
    while True:
        Path('/tmp/worker-heartbeat').touch()
        if next_job():
            continue
        try:
            queue.blpop(QUEUE, timeout=2)
        except RedisError:
            time.sleep(2)


if __name__ == '__main__':
    main()
