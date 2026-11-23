import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select

from src.config.database import Base, Session, engine
from src.constants.enums import IntakeState, Role, Status
from src.models.entities import Analysis, Batch, Capture, Segment, User
from src.services.business import record, snapshot_record, utc_for_storage
from src.utils.security import password_hash

REGIONS = [('BANK-01','柳渡段','南岸',True,range(1,31),range(13,39)),
           ('BANK-02','石桥段','北岸',True,range(1,18),[1,18,19,20,21,22,23,24]),
           ('BANK-03','船坞段','南岸',False,range(1,13),range(7,16)),
           ('BANK-04','芦廊段','北岸',True,range(1,20),range(8,19))]
CODE = 'NOV21-BENCH'
# 周末早班采集窗口为现场时间 07:00–10:30。
FIELD_TIMEZONE = timezone(timedelta(hours=8))
WINDOW_FROM = utc_for_storage(datetime(2026, 11, 21, 7, 0, tzinfo=FIELD_TIMEZONE))
WINDOW_TO = utc_for_storage(datetime(2026, 11, 21, 10, 30, tzinfo=FIELD_TIMEZONE))


def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in Role:
            email = f'{role}@tingyan.demo'
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, role=role, password_hash=password_hash('BankBench2026!')))
        known = set(db.scalars(select(Segment.code)))
        db.add_all(Segment(code=code, title=title, bank=bank, stable=stable)
                   for code,title,bank,stable,*_ in REGIONS if code not in known)
        db.flush()
        if not db.scalar(select(Batch).where(Batch.campaign == CODE)):
            db.add(Batch(campaign=CODE, title='周末早班 · 滨江步道座椅清点',
                         collected_from=WINDOW_FROM, collected_to=WINDOW_TO,
                         closed_at=WINDOW_TO, version=0))
        db.flush()
        prior = set(db.execute(select(Capture.segment_code, Capture.round_code, Capture.asset_code)
                               .where(Capture.campaign == CODE)).tuples())
        for code, _, _, _, first, second in REGIONS:
            for cycle, sample in (('A',first),('B',second)):
                for number in sample:
                    asset = f'{code}-S{number:03d}'
                    if (code,cycle,asset) not in prior:
                        state = 'unverified' if (code,cycle,number) == ('BANK-04','B',17) else 'verified'
                        stamp = WINDOW_FROM + timedelta(minutes=number * 2)
                        db.add(Capture(segment_code=code, campaign=CODE, round_code=cycle,
                                       asset_code=asset, state=state,
                                       client_ref=f'seed-{code}-{cycle}-{number:03d}',
                                       collected_at=stamp, received_at=stamp,
                                       intake_state=IntakeState.CURRENT))
        db.flush()
        title = '周末早班 · 滨江补巡清单'
        if not db.scalar(select(Analysis).where(Analysis.title == title)):
            owner = db.scalar(select(User).where(User.role == Role.ANALYST))
            params = {'campaign':CODE,'min_overlap':5,'verified_independence':True,
                      'segments':[record(row) for row in db.scalars(select(Segment).order_by(Segment.code))]}
            snapshot = [snapshot_record(row) for row in db.scalars(select(Capture).where(
                Capture.campaign == CODE, Capture.intake_state == IntakeState.CURRENT))]
            batch = db.scalar(select(Batch).where(Batch.campaign == CODE))
            batch.version = 1
            db.add(Analysis(title=title, status=Status.QUEUED, author_id=owner.id,
                            parameters=params, snapshot=snapshot, result=None,
                            campaign=CODE, version=1, is_effective=True,
                            trigger='initial', supplement_ids=[]))
        db.commit()
        return {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                for model in (User, Segment, Batch, Capture, Analysis)}


if __name__ == '__main__':
    print(json.dumps(seed(), sort_keys=True))
