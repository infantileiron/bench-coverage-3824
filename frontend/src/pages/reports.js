import {api} from '../api/survey.js';
import {heading} from '../components/common/layout.js';
import {metrics} from '../components/common/metrics.js';
import {table} from '../components/common/table.js';
import {states, triggers} from '../constants/enums.js';
import {onForm} from '../hooks/forms.js';
import {session} from '../stores/session.js';
import {h} from '../utils/html.js';

function fmt(value) {
  return value === null || value === undefined ? '—' : String(value);
}

export async function reports(id) {
  const [list, batches] = await Promise.all([api.analyses(), api.batches()]);
  const run = id || list.length ? await api.analysis(id || list[0].id) : null;
  const batchInfo = run?.campaign ? batches.find(x => x.campaign === run.campaign) : null;
  const sidebar = `<aside class="sheet"><h2>补巡单</h2><ul class="runs">${list.map(x =>
    `<li><a href="#reports/${x.id}">${h(x.title)} v${x.version}</a><span>${h(states[x.status])}${x.is_effective ? ' · 有效' : ''}</span></li>`).join('')
    || '<li>暂无补巡单。</li>'}</ul></aside>`;
  let content = '<div class="empty">先在 <a href="#analyze">漏查估算</a> 锁定双轮记录快照。</div>';
  if (run) {
    const output = run.result;
    const versionTag = run.is_effective
      ? '<span class="badge effective">当前有效版本</span>'
      : '<span class="badge stale">历史版本 · 保留原口径</span>';
    const supplementBadge = batchInfo && (batchInfo.pending_count > 0)
      ? `<span class="badge pending">补入队列 ${h(batchInfo.pending_count)} 条待重算</span>` : '';
    content = `<h2>${h(run.title)} <small>v${h(run.version)}</small></h2>
      <p class="state">${h(states[run.status])} · ${h(triggers[run.trigger] || run.trigger)} ${versionTag} ${supplementBadge}</p>
      ${batchInfo ? `<p class="hint">批次 ${h(run.campaign)}：采集 ${new Date(batchInfo.collected_from).toLocaleString('zh-CN',{hour12:false})} ～ ${new Date(batchInfo.collected_to).toLocaleString('zh-CN',{hour12:false})}；累计补入 ${h(batchInfo.supplemented_count)} 条。</p>` : ''}`;
    if (output) {
      const columns = ['区段','A 轮','B 轮','重合','合并实见','估计总量','估计漏查','估计方差','建议'];
      content += `${metrics(output.metrics)}<p class="decision">${h(output.summary)}</p>
        <h3>按区段的实见与漏查</h3><div class="tall">${table(columns, output.rows.map(row => columns.map(key => row[key])))}</div>`;
      if (run.diff) {
        const d = run.diff;
        content += `<h3>补入差异 · 相对上一有效版本</h3>
          <p class="hint">本版补入 ${h(d.supplement_count)} 条迟到记录；可估区段漏查合计 ${fmt(d.old_total_missed)} → ${fmt(d.new_total_missed)}（变化 ${fmt(d.total_missed_delta)}）。</p>
          <div class="tall">${table(['区段','旧版实见','新版实见','旧版漏查','新版漏查','漏查变化'],
            d.segment_misses.map(x => [x.区段, fmt(x.旧版实见), fmt(x.新版实见), fmt(x.旧版漏查), fmt(x.新版漏查), fmt(x.漏查变化)]))}</div>
          <h4>本次补入记录</h4>
          <div>${table(['区段编号','轮次','座椅编号','标签状态','采集时间','回传时间'], d.supplement_records.map(x => [
            x.区段编号, x.轮次, x.座椅编号, states[x.标签状态] || x.标签状态,
            new Date(x.采集时间).toLocaleString('zh-CN',{hour12:false}),
            new Date(x.回传时间).toLocaleString('zh-CN',{hour12:false})]))}</div>`;
      }
      content += `<ul class="notes">${output.notes.map(note => `<li>${h(note)}</li>`).join('')}</ul>
        ${run.note ? `<p class="signed">签核意见 · ${h(run.note)}</p>` : ''}
        <button class="secondary" id="export">下载补巡派发表（含差异与有效版本）</button><p id="export-error" role="alert"></p>`;
      if (session()?.role === 'manager' && run.status === 'completed' && run.is_effective) {
        content += `<form id="publish-form"><label>签核意见<input name="note" required minlength="3"></label><button type="submit">签核派发</button><p role="alert"></p></form>`;
      } else if (session()?.role === 'manager' && run.status === 'completed' && !run.is_effective) {
        content += `<p class="hint">该版本已被新版替代，仅保留原口径，不能签核；请在当前有效版本签核。</p>`;
      }
    } else {
      content += `<p>${h(run.note || 'Worker 正在读取锁定的双轮记录快照，页面将自动刷新。')}</p>`;
    }
  }
  return {
    html:heading('补巡派发','核对优先补巡范围。补入重算成功后一次性切换有效版本，失败保留旧版；旧派发表始终保留原口径。') + `<div class="workarea"> <section class="sheet" id="report">${content}</section>${sidebar}</div>`,
    bind(root, refresh, signal) {
      if (run && ['queued','running'].includes(run.status)) {
        const timer = setTimeout(refresh, 900);
        signal.addEventListener('abort', () => clearTimeout(timer));
      }
      root.querySelector('#export')?.addEventListener('click', async () => {
        try {
          const url = URL.createObjectURL(await api.export(run.id));
          const link = document.createElement('a');
          link.href = url;
          link.download = `bench-plan-${run.id}-v${run.version}.csv`;
          link.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) { root.querySelector('#export-error').textContent = error.message; }
      });
      onForm(root.querySelector('#publish-form'), async data => { await api.publish(run.id, data.note); refresh(); });
    }
  };
}
