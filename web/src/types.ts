/** Types partagés (miroir des schémas Pydantic côté backend). */

export type RunMode = "chat" | "graph" | "exploration";

export interface RunRequest {
  prompt: string;
  mode: RunMode;
  model_id?: string;
  tool_names?: string[];
  skill_name?: string;
  max_steps?: number;
}

export interface RunResponse {
  run_id: string;
  status: "started";
}

export interface RunEvent {
  type: "step" | "tool_call" | "observation" | "token_usage" | "final" | "error" | "status";
  run_id: string;
  data: Record<string, unknown>;
}

export interface StepData {
  step_number: number;
  tool_calls?: { name: string; arguments: string; id?: string }[];
  observations?: string;
  code_action?: string;
  duration_s?: number;
  input_tokens?: number;
  output_tokens?: number;
  error?: string;
  final_output?: string;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  ollama_reachable: boolean;
  models_configured: { fast: string; reasoning: string };
  tools_available: string[];
  skills_available: { name: string; description: string }[];
  mcp_servers: { name: string; configured: boolean; transport: string }[];
}

export interface KgSnapshot {
  entities: { id: string; kind: string; name: string | null }[];
  claims: {
    id: number; entity_id: string; content: string; kind: string;
    confidence: number | null; status: string;
  }[];
  provenance: { claim_id: number; source: string; model_id: string | null }[];
  edges: { src: number; dst: number; relation: string }[];
}
