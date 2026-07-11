import { Router } from 'express';
import fetch from 'node-fetch';
import type { Readable } from 'stream';
import { pool } from '../db/pool';
import { config } from '../config';
import { requireAuth } from '../middleware/auth';

export const chatRouter = Router();

interface ChatRequestBody {
  sessionId?: string | null;
  language?: 'python' | 'java' | 'javascript' | null;
  errorLog?: string | null;
  code?: unknown;
}

// One line of the Orchestrator's newline-delimited JSON stream — CONTRACT.md
// §2 "SSE Event Shapes". Only the `final_fix` shape is inspected here (to
// persist the assistant's reply); every other shape is passed through
// unchanged.
interface FinalFixEvent {
  type: 'final_fix';
  code: string;
  explanation: string;
  language: string;
}

function isFinalFixEvent(value: unknown): value is FinalFixEvent {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { type?: unknown }).type === 'final_fix'
  );
}

// CONTRACT.md §1 POST /api/v1/chat
chatRouter.post('/api/v1/chat', requireAuth, async (req, res) => {
  const body = req.body as ChatRequestBody;
  const userId = req.user!.sub;

  const code = typeof body.code === 'string' ? body.code : null;
  if (!code) {
    res.status(400).json({ error: 'code is required' });
    return;
  }
  const language = body.language ?? null;
  const errorLog = body.errorLog ?? null;

  let sessionId = body.sessionId ?? null;

  try {
    // 1. Create a new session row if none was supplied.
    if (!sessionId) {
      const created = await pool.query<{ id: string }>(
        'INSERT INTO sessions (user_id) VALUES ($1) RETURNING id',
        [userId]
      );
      sessionId = created.rows[0].id;
    } else {
      // Validate the session belongs to this user before writing to it.
      const owned = await pool.query('SELECT id FROM sessions WHERE id = $1 AND user_id = $2', [
        sessionId,
        userId,
      ]);
      if (owned.rowCount === 0) {
        res.status(404).json({ error: 'session_not_found' });
        return;
      }
    }

    // 2. Persist the incoming user message.
    await pool.query(
      'INSERT INTO chat_messages (session_id, role, content) VALUES ($1, $2, $3)',
      [sessionId, 'user', code]
    );
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(JSON.stringify({ event: 'chat_setup_error', message: (err as Error).message, timestamp: new Date().toISOString() }));
    res.status(500).json({ error: 'internal_error' });
    return;
  }

  // 3. Proxy to the Orchestrator (CONTRACT.md §3) and stream its
  // newline-delimited JSON response back as SSE, line by line, without
  // buffering the whole response first.
  let upstream;
  try {
    upstream = await fetch(`${config.orchestratorUrl}/internal/v1/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId, userId, language, errorLog, code }),
    });
  } catch (err) {
    res.status(502).json({ error: 'orchestrator_unreachable' });
    // eslint-disable-next-line no-console
    console.error(JSON.stringify({ event: 'orchestrator_unreachable', message: (err as Error).message, timestamp: new Date().toISOString() }));
    return;
  }

  if (!upstream.ok || !upstream.body) {
    res.status(502).json({ error: 'orchestrator_error' });
    return;
  }

  // node-fetch@2 types `body` as the generic `NodeJS.ReadableStream`, but at
  // runtime it is always a real `stream.Readable` — narrow once here so the
  // rest of this handler can use `.destroy()` and typed 'data'/'end'/'error'
  // listeners without repeated casts.
  const upstreamBody = upstream.body as Readable;

  res.status(200);
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();

  let finalFixContent: string | null = null;
  let buffer = '';

  const persistFinalFix = async (): Promise<void> => {
    if (finalFixContent === null) return;
    try {
      await pool.query(
        'INSERT INTO chat_messages (session_id, role, content) VALUES ($1, $2, $3)',
        [sessionId, 'assistant', finalFixContent]
      );
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(JSON.stringify({ event: 'persist_final_fix_error', message: (err as Error).message, timestamp: new Date().toISOString() }));
    }
  };

  const emitLine = (line: string): void => {
    const trimmed = line.trim();
    if (!trimmed) return;

    // Re-emit unchanged, one SSE `data:` frame per ndjson line.
    res.write(`data: ${trimmed}\n\n`);

    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (isFinalFixEvent(parsed)) {
        finalFixContent = parsed.code;
      }
    } catch {
      // Not valid JSON on this line — pass it through as-is (already
      // written above) but nothing to capture for persistence.
    }
  };

  upstreamBody.on('data', (chunk: Buffer) => {
    buffer += chunk.toString('utf8');
    let newlineIndex: number;
    // eslint-disable-next-line no-cond-assign
    while ((newlineIndex = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, newlineIndex);
      buffer = buffer.slice(newlineIndex + 1);
      emitLine(line);
    }
  });

  upstreamBody.on('end', () => {
    if (buffer.trim()) {
      emitLine(buffer);
    }
    void persistFinalFix().finally(() => {
      res.end();
    });
  });

  upstreamBody.on('error', (err: Error) => {
    // eslint-disable-next-line no-console
    console.error(JSON.stringify({ event: 'upstream_stream_error', message: err.message, timestamp: new Date().toISOString() }));
    res.write(`data: ${JSON.stringify({ type: 'error', message: 'upstream_stream_error' })}\n\n`);
    void persistFinalFix().finally(() => {
      res.end();
    });
  });

  req.on('close', () => {
    // Browser disconnected early — stop reading from the Orchestrator.
    upstreamBody.destroy();
  });
});

interface ChatMessageRow {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning_tokens: string | null;
  created_at: Date;
}

// CONTRACT.md §1 GET /api/v1/chat/:sessionId/history
chatRouter.get('/api/v1/chat/:sessionId/history', requireAuth, async (req, res) => {
  const { sessionId } = req.params;
  const userId = req.user!.sub;

  try {
    const owned = await pool.query('SELECT id FROM sessions WHERE id = $1 AND user_id = $2', [
      sessionId,
      userId,
    ]);
    if (owned.rowCount === 0) {
      res.status(404).json({ error: 'session_not_found' });
      return;
    }

    const result = await pool.query<ChatMessageRow>(
      'SELECT id, role, content, reasoning_tokens, created_at FROM chat_messages WHERE session_id = $1 ORDER BY created_at ASC',
      [sessionId]
    );

    res.status(200).json({
      sessionId,
      messages: result.rows.map((row) => ({
        id: row.id,
        role: row.role,
        content: row.content,
        reasoningTokens: row.reasoning_tokens,
        createdAt: row.created_at.toISOString(),
      })),
    });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(JSON.stringify({ event: 'history_error', message: (err as Error).message, timestamp: new Date().toISOString() }));
    res.status(500).json({ error: 'internal_error' });
  }
});
