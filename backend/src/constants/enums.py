from enum import StrEnum


class Role(StrEnum):
    MANAGER = 'manager'
    ANALYST = 'analyst'
    VIEWER = 'viewer'


class Status(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    PUBLISHED = 'published'


class IntakeState(StrEnum):
    # 随批次采集窗口内回传，已进入当批台账
    CURRENT = 'current'
    # 窗口关闭后才回传，进入对应批次的补入队列
    PENDING = 'pending'
    # 已通过补入流程写入批次快照（重算版本）
    SUPPLEMENTED = 'supplemented'
