import {api} from '../api/survey.js';
import {heading} from '../components/common/layout.js';
import {table} from '../components/common/table.js';
import {intakeStates, states, triggers} from '../constants/enums.js';
import {onForm} from '../hooks/forms.js';
import {canWrite} from '../stores/session.js';
import {h} from '../utils/html.js';

let selectedCampaign = null;

function toLocalInput(value) {
  if (!value) return '';
  return new Date(new Date(value).getTime() - new Date().getTimezoneOffset() * 60000)
    .toISOString().slice(0, 16);
}

function toIso(localValue) {
  return new Date(localValue).toISOString();
}

export async function batches() {
  const [list, analyses] = await Promise.all([api.batches(), api.analyses()]);
  const chosen = list.find(x => x.campaign === selectedCampaign) || list[0];
  selectedCampaign = chosen?.campaign || null;
  const queue = chosen ? await api.supplements(chosen.campaign) : [];
  const chain = chosen ? analyses.filter(x => x.campaign === chosen.campaign) : [];

  const form = `<section class="sheet tools"><h2>建立批次采集时段</h2>
    <p>同一批次按实际采集时段归集；窗口关闭后回传的记录进入补入队列，不混入当批。</p>
    <form id="batch-form">
      <label>批次编号<input name="campaign" required pattern="[A-Z0-9-]+" placeholder="NOV22-BENCH"></label>
      <label>批次名称<input name="title" required placeholder="周日早班 · 滨江步道"></label>
      <label>采集开始<input name="collected_from" type="datetime-local" required></label>
      <label>采集结束<input name="collected_to" type="datetime-local" required></label>
      <button type="submit">登记批次</button><p role="alert"></p>
    </form></section>`;

  const listRows = list.map(x => [
    x.campaign, x.title,
    `${toLocalInput(x.collected_from).replace('T', ' ')} ～ ${toLocalInput(x.collected_to).replace('T', ' ')}`,
    `v${x.version}`,
    x.pending_count ? `补入队列 ${x.pending_count} 条` : '无待补入',
    `已补入 ${x.supplemented_count} 条`,
  ]);

  const queuePanel = chosen ? `<section class="sheet"><h2>补入队列 · ${h(chosen.title)}</h2>
    <p>采集时段落在窗口外、跨日回传的迟到记录。发起重算后将一次性纳入新版本。</p>
    ${table(['区段','轮次','座椅编号','标签状态','去重键','采集时间','归集状态'], queue.map(x => [
      x.segment_code, x.round_code, x.asset_code, states[x.state] || x.state,
      x.client_ref, toLocalInput(x.collected_at).replace('T', ' '), intakeStates[x.intake_state] || x.intake_state,
    ]), '补入队列为空，当前没有迟到记录。')}
    ${canWrite() ? `<form id="recalc-form"><button type="submit" ${queue.length ? '' : 'disabled'}>按补入队列重算派发表</button><p role="alert"></p></form>` : ''}
    <h3>版本链（旧版保留原口径）</h3>
    ${table(['版本','来源','状态','是否有效'], chain.map(x => [
      `v${x.version}`, triggers[x.trigger] || x.trigger, states[x.status] || x.status,
      x.is_effective ? '当前有效' : '历史版本',
    ]), '该批次还没有派发表版本。')}
    ${chain.length ? `<p><a class="secondary-link" href="#reports/${h(chain[0].id)}">打开补巡派发页 →</a></p>` : ''}
  </section>` : '<section class="sheet">先建立一个巡查批次。</section>';

  return {html: heading('巡查批次', '按实际采集时段归集座椅记录，管理迟到补入队列与派发表版本切换。') +
      `<div class="workarea"><section class="sheet"><h2>批次台账</h2>
      ${table(['批次编号','名称','采集时段','当前版本','补入状态','累计补入'], listRows, '还没有批次。')}
      ${list.length ? `<p class="hint">在下方选择批次查看补入队列：${list.map(x =>
        `<button class="chip ${x.campaign === selectedCampaign ? 'on' : ''}" data-campaign="${h(x.campaign)}">${h(x.campaign)}</button>`).join('')}</p>` : ''}
      </section>${canWrite() ? form : ''}${queuePanel}</div>`,
    bind(root, refresh) {
      root.querySelectorAll('.chip').forEach(btn => btn.addEventListener('click', () => {
        selectedCampaign = btn.dataset.campaign; refresh();
      }));
      onForm(root.querySelector('#batch-form'), async data => {
        await api.batches({...data,
          collected_from: toIso(data.collected_from),
          collected_to: toIso(data.collected_to)});
        refresh();
      });
      onForm(root.querySelector('#recalc-form'), async () => {
        const run = await api.recalculate(chosen.campaign);
        location.hash = `reports/${run.id}`;
      });
    }};
}
