import {api} from '../api/survey.js';
import {heading} from '../components/common/layout.js';
import {table} from '../components/common/table.js';
import {strip} from '../components/common/strip.js';
import {intakeStates, states} from '../constants/enums.js';
import {onForm} from '../hooks/forms.js';
import {canWrite} from '../stores/session.js';
import {h} from '../utils/html.js';

let selected = 'BANK-01';
let campaign = 'NOV21-BENCH';
let intakeFilter = '';

function localNow() {
  return new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function toIso(localValue) {
  // datetime-local 按浏览器本地时区解析，toISOString 即对应 UTC
  return new Date(localValue).toISOString();
}

export async function captures() {
  const segments = await api.segments();
  const chosen = segments.find(x => x.code === selected) || segments[0];
  if (!chosen) return {html:heading('双轮发现清单','先登记区段与批次采集时段，再记录两轮独立发现。')};
  const [rows, summary] = await Promise.all([
    api.captures(chosen.code, campaign, intakeFilter || undefined),
    api.summary(chosen.code, campaign)]);
  const pending = rows.filter(x => x.state === 'unverified');
  const form = `<section class="sheet tools"><h2>记录座椅标签</h2><p>${h(chosen.title)} · ${h(campaign)}</p>
    <p class="hint">实际采集时间落在批次窗口外会自动进入补入队列；去重键用于设备重试/整批重送去重，同一条记录重发必须保持不变。</p>
    <form id="capture-form">
      <label>巡视轮次<select name="round_code"><option>A</option><option>B</option></select></label>
      <label>座椅编号<input name="asset_code" required placeholder="BANK-01-S099"></label>
      <label>实际采集时间<input name="collected_at" type="datetime-local" required value="${localNow()}"></label>
      <label>去重键（设备生成，重试保持不变）<input name="client_ref" required pattern="[A-Za-z0-9:_-]{4,80}" value="dev-${crypto.randomUUID()}"></label>
      <label>核对状态<select name="state"><option value="verified">标签已核</option><option value="unverified">待核标签</option></select></label>
      <button type="submit">登记发现</button><p role="alert"></p></form>
    ${pending.length ? `<form id="confirm-form"><h3>待核照片</h3><label>座椅标签<select name="id">${pending.map(x => `<option value="${x.id}">${h(x.round_code)} · ${h(x.asset_code)}</option>`).join('')}</select></label><button type="submit">确认实物编号</button><p role="alert"></p></form>` : ''}</section>`;
  return {html:heading('双轮发现清单','独立记录同一物理标签。跨日迟到记录进入对应批次的补入队列，不混入当批口径。') +
    `<div class="workarea"><section class="sheet"><h2>发现台账 · ${h(chosen.title)}</h2><form id="filter-form" class="filters">
    <label>区段<select name="segment">${segments.map(x => `<option value="${h(x.code)}" ${chosen.code === x.code ? 'selected' : ''}>${h(x.title)}</option>`).join('')}</select></label>
    <label>巡查批次<input name="campaign" required pattern="[A-Z0-9-]+" value="${h(campaign)}"></label>
    <label>归集状态<select name="intake_state"><option value="">全部</option><option value="current">当批台账</option><option value="pending">补入队列</option><option value="supplemented">已补入</option></select></label>
    <button type="submit" class="secondary">查询</button><p role="alert"></p></form>
    ${strip(summary)}<div class="tall">${table(['轮次','座椅编号','标签状态','归集状态','去重键','采集时间'],rows.map(x => [
      x.round_code, x.asset_code, states[x.state] || x.state,
      intakeStates[x.intake_state] || x.intake_state, x.client_ref,
      x.collected_at ? new Date(x.collected_at).toLocaleString('zh-CN', {hour12:false}) : '']
    ))}</div></section>${canWrite()?form:''}</div>`,
    bind(root, refresh) {
      onForm(root.querySelector('#filter-form'), async data => {
        selected = data.segment; campaign = data.campaign; intakeFilter = data.intake_state || '';
        refresh();
      });
      onForm(root.querySelector('#capture-form'), async data => {
        await api.addCapture({...data, segment_code:chosen.code, campaign,
          collected_at: toIso(data.collected_at)});
        refresh();
      });
      onForm(root.querySelector('#confirm-form'), async data => {await api.confirm(data.id); refresh();});
    }
  };
}
