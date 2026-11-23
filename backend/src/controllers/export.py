import csv
import io
from sqlalchemy import select

from fastapi import HTTPException, Response

from src.models.entities import Analysis


def safe(value):
    if value is None:
        return ''
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def export(item, db):
    if not item.result:
        raise HTTPException(409, '估算结果尚未完成')
    effective = db.scalar(select(Analysis).where(
        Analysis.campaign == item.campaign,
        Analysis.is_effective.is_(True))) if item.campaign else item
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['补巡单', '状态', '结论'])
    writer.writerow([safe(item.title), item.status, safe(item.result['summary'])])
    writer.writerow([])
    # 当前有效版本信息
    writer.writerow(['版本信息'])
    writer.writerow(['批次', safe(item.campaign or '')])
    writer.writerow(['本单版本', f'v{item.version}'])
    writer.writerow(['当前有效版本', f'v{effective.version}' if effective else ''])
    writer.writerow(['本单是否有效', '是' if item.is_effective else '否（已被新版替代，保留原口径）'])
    writer.writerow(['版本来源', '补入重算' if item.trigger == 'supplement' else '初始估算'])
    writer.writerow([])

    for key, value in item.result['metrics'].items():
        writer.writerow([key, value])
    rows = item.result['rows']
    if rows:
        writer.writerow([])
        columns = ['区段', 'A 轮', 'B 轮', '重合', '合并实见', '估计总量', '估计漏查', '估计方差', '建议']
        writer.writerow(columns)
        writer.writerows([safe(row[key]) for key in columns] for row in rows)

    if item.diff:
        diff = item.diff
        writer.writerow([])
        writer.writerow(['补入差异（本版相对上一有效版本）'])
        writer.writerow(['补入记录数', diff['supplement_count'],
                         '漏查合计变化', safe(diff['total_missed_delta']),
                         '旧版漏查合计', safe(diff['old_total_missed']),
                         '新版漏查合计', safe(diff['new_total_missed'])])
        writer.writerow([])
        miss_columns = ['区段', '旧版实见', '新版实见', '旧版漏查', '新版漏查', '漏查变化']
        writer.writerow(miss_columns)
        for row in diff['segment_misses']:
            writer.writerow([safe(row[key]) for key in miss_columns])
        if diff['supplement_records']:
            writer.writerow([])
            writer.writerow(['补入记录明细'])
            detail_columns = ['区段编号', '轮次', '座椅编号', '标签状态', '采集时间', '回传时间']
            writer.writerow(detail_columns)
            for row in diff['supplement_records']:
                writer.writerow([safe(row[key]) for key in detail_columns])

    return Response(content='﻿' + stream.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="bench-plan-{item.id}-v{item.version}.csv"'})
