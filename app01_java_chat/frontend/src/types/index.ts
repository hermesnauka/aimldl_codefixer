// TypeScript types mirroring CONTRACT.md sections 1-2 exactly.
// Do not invent shapes not present in CONTRACT.md — the Gateway is the only
// service this frontend talks to (see CONTRACT.md "Topology" + section 1).

export type Language = "python" | "java" | "javascript";

// --- POST /api/v1/auth/login ---------------------------------------------

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  username: string;
}

export interface LoginErrorResponse {
  error: "invalid_credentials";
}

// --- POST /api/v1/chat -----------------------------------------------------

export interface ChatRequest {
  /** uuid, or null to let the Gateway create a new session */
  sessionId: string | null;
  language: Language | null;
  /** optional stack trace / compiler output */
  errorLog?: string;
  /** the user's source snippet */
  code: string;
}

// --- GET /api/v1/chat/:sessionId/history -----------------------------------

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoningTokens: string | null;
  createdAt: string;
}

export interface ChatHistoryResponse {
  sessionId: string;
  messages: ChatMessage[];
}

// --- GET /health ------------------------------------------------------------

export interface HealthResponse {
  status: "UP";
}

// --- SSE Event Shapes (CONTRACT.md section 2) -------------------------------
// Discriminated union on `type`, exactly matching CONTRACT.md's JSON shapes.

export type AgentStage =
  | "routing"
  | "reasoning"
  | "executing"
  | "self_correcting"
  | "finalizing";

export interface StatusEvent {
  type: "status";
  stage: AgentStage;
}

export interface ReasoningTokenEvent {
  type: "reasoning_token";
  /** one incremental token of Chain-of-Thought */
  token: string;
}

export interface ProviderFailoverEvent {
  type: "provider_failover";
  from: string;
  to: string;
  reason: string;
}

export interface ExecutionResultEvent {
  type: "execution_result";
  language: string;
  exitCode: number;
  stdout: string;
  stderr: string;
  durationMs: number;
}

export interface FinalFixEvent {
  type: "final_fix";
  code: string;
  explanation: string;
  language: string;
}

export interface ErrorEvent {
  type: "error";
  message: string;
}

export interface DoneEvent {
  type: "done";
}

export type ChatStreamEvent =
  | StatusEvent
  | ReasoningTokenEvent
  | ProviderFailoverEvent
  | ExecutionResultEvent
  | FinalFixEvent
  | ErrorEvent
  | DoneEvent;
