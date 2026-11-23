"""保留数据卷的幂等结构升级。

首次启动由 entities 建表；已存在旧表的数据卷通过这里补齐新列与索引，
全部以 information_schema 判定，重复执行无副作用。
"""
from sqlalchemy import text

from src.config.database import engine


def _column_exists(db, table, column):
    return db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"),
        {'t': table, 'c': column}).first() is not None


def _index_exists(db, index):
    return db.execute(text(
        "SELECT 1 FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND index_name = :i"),
        {'i': index}).first() is not None


def run_migrations():
    with engine.begin() as db:
        capture_columns = {
            'client_ref': "VARCHAR(80) NULL",
            'collected_at': "DATETIME NULL",
            'received_at': "DATETIME NULL",
            'intake_state': "VARCHAR(12) NULL",
        }
        for column, ddl in capture_columns.items():
            if not _column_exists(db, 'survey_captures', column):
                db.execute(text(f"ALTER TABLE survey_captures ADD COLUMN {column} {ddl}"))
        # 旧记录回填：去重键用主键派生，时间沿用当前时间，状态视为当批
        db.execute(text(
            "UPDATE survey_captures SET client_ref = CONCAT('legacy-', id) WHERE client_ref IS NULL"))
        db.execute(text(
            "UPDATE survey_captures SET collected_at = NOW() WHERE collected_at IS NULL"))
        db.execute(text(
            "UPDATE survey_captures SET received_at = NOW() WHERE received_at IS NULL"))
        db.execute(text(
            "UPDATE survey_captures SET intake_state = 'current' WHERE intake_state IS NULL"))
        if not _index_exists(db, 'uq_capture_client_ref'):
            db.execute(text(
                "ALTER TABLE survey_captures ADD UNIQUE INDEX uq_capture_client_ref (client_ref)"))
        if not _index_exists(db, 'ix_survey_captures_intake_state'):
            db.execute(text(
                "ALTER TABLE survey_captures ADD INDEX ix_survey_captures_intake_state (intake_state)"))

        analysis_columns = {
            'campaign': "VARCHAR(32) NULL",
            'version': "INT NOT NULL DEFAULT 1",
            'is_effective': "BOOL NOT NULL DEFAULT 1",
            'trigger': "VARCHAR(12) NOT NULL DEFAULT 'initial'",
            'supplement_ids': "JSON NULL",
            'diff': "JSON NULL",
        }
        for column, ddl in analysis_columns.items():
            if not _column_exists(db, 'coverage_plans', column):
                db.execute(text(f"ALTER TABLE coverage_plans ADD COLUMN {column} {ddl}"))
        if not _index_exists(db, 'ix_coverage_plans_campaign'):
            db.execute(text("ALTER TABLE coverage_plans ADD INDEX ix_coverage_plans_campaign (campaign)"))
        if not _index_exists(db, 'ix_coverage_plans_is_effective'):
            db.execute(text("ALTER TABLE coverage_plans ADD INDEX ix_coverage_plans_is_effective (is_effective)"))
