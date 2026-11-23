/** @typedef {{id: number, code: string, title: string, bank: string, stable: boolean}} Segment */
/** @typedef {{id: number, campaign: string, title: string, collected_from: string, collected_to: string, closed_at: string|null, version: number, pending_count: number, supplemented_count: number}} Batch */
/** @typedef {{id: number, segment_code: string, campaign: string, round_code: 'A'|'B', asset_code: string, state: string, client_ref: string, collected_at: string, received_at: string, intake_state: string}} Capture */
/** @typedef {{id: number, title: string, status: string, note: string, parameters: object, result?: object, campaign?: string, version: number, is_effective: boolean, trigger: string, supplement_ids: number[], diff?: object|null, effective_version?: number}} Analysis */
