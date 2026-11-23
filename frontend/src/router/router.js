import {segments} from '../pages/segments.js';
import {batches} from '../pages/batches.js';
import {captures} from '../pages/captures.js';
import {analyze} from '../pages/analyze.js';
import {reports} from '../pages/reports.js';
const routes = {segments, batches, captures, analyze, reports};
export function route() {
  const [page, id] = location.hash.slice(1).split('/');
  if (Object.hasOwn(routes, page)) return [page, () => routes[page](/^\d+$/.test(id) ? Number(id) : null)];
  return ['segments', segments];
}
