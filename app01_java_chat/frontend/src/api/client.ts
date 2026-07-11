// Typed fetch wrappers for the Gateway API — the frontend's ONLY backend
// dependency (CONTRACT.md "Topology": browser talks only to the Gateway).
import type {
  ChatHistoryResponse,
  ChatRequest,
  HealthResponse,
  LoginErrorResponse,
  LoginRequest,
  LoginResponse,
} from "../types";

const GATEWAY_URL: string =
  (import.meta.env.VITE_GATEWAY_URL as string | undefined) ??
  "http://localhost:4000";

const TOKEN_STORAGE_KEY = "codefixer.token";
const USERNAME_STORAGE_KEY = "codefixer.username";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function getStoredUsername(): string | null {
  return localStorage.getItem(USERNAME_STORAGE_KEY);
}

export function storeSession(token: string, username: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
  localStorage.setItem(USERNAME_STORAGE_KEY, username);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USERNAME_STORAGE_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * POST /api/v1/auth/login
 * 200 -> {token, username}; 401 -> {error: "invalid_credentials"}
 */
export async function login(
  credentials: LoginRequest,
): Promise<LoginResponse> {
  const res = await fetch(`${GATEWAY_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  });

  if (res.status === 401) {
    const body = (await res.json()) as LoginErrorResponse;
    throw new ApiError(body.error, 401);
  }
  if (!res.ok) {
    throw new ApiError(`Login failed with status ${res.status}`, res.status);
  }
  return (await res.json()) as LoginResponse;
}

/**
 * GET /api/v1/chat/:sessionId/history
 */
export async function getChatHistory(
  sessionId: string,
): Promise<ChatHistoryResponse> {
  const token = getStoredToken();
  const res = await fetch(
    `${GATEWAY_URL}/api/v1/chat/${encodeURIComponent(sessionId)}/history`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    },
  );
  if (!res.ok) {
    throw new ApiError(
      `Failed to load history: ${res.status}`,
      res.status,
    );
  }
  return (await res.json()) as ChatHistoryResponse;
}

/**
 * GET /health
 */
export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${GATEWAY_URL}/health`);
  if (!res.ok) {
    throw new ApiError(`Health check failed: ${res.status}`, res.status);
  }
  return (await res.json()) as HealthResponse;
}

/**
 * Returns the raw fetch Response for POST /api/v1/chat so the caller
 * (useChatStream) can read its body as a stream. Kept here so every
 * Gateway URL / auth-header concern lives in one file.
 */
export async function postChat(
  request: ChatRequest,
  signal?: AbortSignal,
): Promise<Response> {
  const token = getStoredToken();
  const res = await fetch(`${GATEWAY_URL}/api/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(request),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new ApiError(
      `Chat stream request failed: ${res.status}`,
      res.status,
    );
  }
  return res;
}

export { GATEWAY_URL };
