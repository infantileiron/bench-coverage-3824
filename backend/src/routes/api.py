from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.config.database import get_db
from src.controllers.auth import current, login, manager, writable
from src.controllers.export import export
from src.models.entities import Analysis, Audit, Batch, Segment, Capture
from src.schemas.business import (AnalysisInput, BatchInput, CaptureInput,
                                  Login, Publication, SegmentInput)
from src.services import business as svc
from src.services.coverage import capture_counts, group_captures

router = APIRouter(prefix='/api')


@router.post('/auth/login')
def sign_in(data: Login, db=Depends(get_db)):
    return login(data, db)


@router.get('/auth/me')
def me(user=Depends(current)):
    return {'email': user.email, 'role': user.role}


@router.get('/segments')
def segments(db=Depends(get_db), user=Depends(current)):
    return [svc.record(item) for item in db.scalars(select(Segment).order_by(Segment.code))]


@router.post('/segments', status_code=201)
def create_segment(data: SegmentInput, db=Depends(get_db), user=Depends(writable)):
    return svc.save_segment(db, data, user)


@router.get('/batches')
def batches(db=Depends(get_db), user=Depends(current)):
    return svc.list_batches(db)


@router.post('/batches', status_code=201)
def create_batch(data: BatchInput, db=Depends(get_db), user=Depends(writable)):
    return svc.create_batch(db, data, user)


@router.get('/batches/{campaign}/supplements')
def supplement_queue(campaign: str, db=Depends(get_db), user=Depends(current)):
    return svc.supplement_queue(db, campaign)


@router.post('/batches/{campaign}/recalculate', status_code=202)
def recalculate(campaign: str, db=Depends(get_db), user=Depends(writable)):
    return svc.recalc_with_supplements(db, campaign, user)


@router.get('/captures')
def captures(campaign: str | None = None, segment_code: str | None = None,
             intake_state: str | None = None, db=Depends(get_db), user=Depends(current)):
    query = select(Capture).order_by(Capture.id.desc())
    if campaign:
        query = query.where(Capture.campaign == campaign)
    if segment_code:
        query = query.where(Capture.segment_code == segment_code)
    if intake_state:
        query = query.where(Capture.intake_state == intake_state)
    return [svc.record(item) for item in db.scalars(query)]


@router.get('/captures/summary')
def summary(campaign: str, segment_code: str, db=Depends(get_db), user=Depends(current)):
    query = select(Capture).where(Capture.campaign == campaign, Capture.segment_code == segment_code)
    captures = (svc.record(item) for item in db.scalars(query))
    return capture_counts(group_captures(captures)[segment_code])


@router.post('/captures', status_code=201)
def create_capture(data: CaptureInput, db=Depends(get_db), user=Depends(writable)):
    return svc.save_capture(db, data, user)


@router.post('/captures/{id}/verify')
def verify_capture(id: int, db=Depends(get_db), user=Depends(writable)):
    return svc.verify_capture(db, id, user)


@router.get('/analyses')
def analyses(db=Depends(get_db), user=Depends(current)):
    return [svc.record(item, ('snapshot', 'result')) for item in db.scalars(select(Analysis).order_by(Analysis.id.desc()))]


@router.post('/analyses', status_code=202)
def enqueue(data: AnalysisInput, db=Depends(get_db), user=Depends(writable)):
    return svc.submit(db, data, user)


@router.get('/analyses/{id}')
def analysis(id: int, db=Depends(get_db), user=Depends(current)):
    item = svc.get_analysis(db, id)
    data = svc.record(item, ('snapshot',))
    if item.campaign:
        data['effective_version'] = db.scalar(
            select(Analysis.version).where(Analysis.campaign == item.campaign,
                                           Analysis.is_effective.is_(True)))
    return data


@router.get('/analyses/{id}/export')
def download(id: int, db=Depends(get_db), user=Depends(current)):
    return export(svc.get_analysis(db, id), db)


@router.post('/analyses/{id}/publish')
def publish(id: int, data: Publication, db=Depends(get_db), user=Depends(manager)):
    return svc.publish(db, id, data.note, user)


@router.get('/audits')
def audit_log(db=Depends(get_db), user=Depends(manager)):
    return [svc.record(item) for item in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100))]
