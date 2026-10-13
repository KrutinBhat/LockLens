export interface ScenarioVersion {
  id: number; version: number; definition: ScenarioDefinition; change_note: string; created_at: string;
}
export interface Scenario {
  id: number; project_id: number | null; is_template: boolean; key: string; name: string;
  category: string; description: string; created_at: string; latest_version: ScenarioVersion | null;
}
export interface StepDef { kind: "sql" | "checkpoint" | "commit" | "rollback"; sql?: string; name?: string; save_as?: string; }
export interface TxDef { name: string; isolation: string; steps: StepDef[]; }
export interface InvariantDef { name: string; sql: string; expect: string; }
export interface ScenarioDefinition {
  seed_sql: string[]; transactions: TxDef[]; invariants: InvariantDef[]; final_state_sql?: string | null;
}
export interface TxSession {
  tx_name: string; isolation_level: string; backend_pid: number | null; outcome: string;
  error_sqlstate: string | null; error_message: string;
}
export interface ExecutionEvent {
  seq: number; tx_name: string | null; kind: string; step_index: number | null;
  sql_text: string; result: any; duration_ms: number | null; at: string;
}
export interface RunMetric {
  wall_time_ms: number; total_lock_wait_ms: number; max_lock_wait_ms: number; steps_executed: number;
  commits: number; rollbacks: number; deadlocks: number; serialization_failures: number; invariant_violations: number;
}
export interface Finding {
  detector: string; status: "confirmed" | "potential" | "inconclusive"; severity: string;
  summary: string; evidence_event_seqs: number[]; detail: any;
}
export interface Run {
  id: number; scenario_id: number; scenario_version_id: number; status: string;
  started_at: string | null; finished_at: string | null; error: string;
  analysis: { findings: Finding[]; anomaly_detected: boolean; scope_note?: string };
  created_at: string; sessions: TxSession[]; metrics: RunMetric | null;
}
export interface RunDetail extends Run {
  events: ExecutionEvent[];
  dependency_edges: { from_tx: string; to_tx: string; kind: string; evidence: any }[];
  lock_snapshots: { at: string; locks: any[] }[];
}
export interface Comparison {
  id: number; name: string; baseline_run_id: number | null; candidate_run_id: number | null;
  change: any; verdict: any; created_at: string;
}
export interface Page<T> { items: T[]; total: number; page: number; page_size: number; }
