import {send} from './client.js';
export const api = {
  login: data => send('/auth/login', data),
  segments: input => send('/segments', input),
  batches: input => send('/batches', input),
  supplements: campaign => send(`/batches/${encodeURIComponent(campaign)}/supplements`),
  recalculate: campaign => send(`/batches/${encodeURIComponent(campaign)}/recalculate`, {}),
  captures: (code, campaign, intakeState) => send(`/captures?${new URLSearchParams({segment_code:code, campaign, ...(intakeState ? {intake_state:intakeState} : {})})}`),
  summary: (code, campaign) => send(`/captures/summary?${new URLSearchParams({segment_code:code, campaign})}`),
  addCapture: input => send('/captures', input),
  confirm: id => send(`/captures/${id}/verify`, {}),
  analyses: input => send('/analyses', input),
  analysis: id => send(`/analyses/${id}`),
  publish: (id, note) => send(`/analyses/${id}/publish`, {note}),
  export: id => send(`/analyses/${id}/export`, undefined, true),
};
