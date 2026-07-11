import { NextFunction, Request, Response } from 'express';

// Phase 1 "asynchronous audit log writing" (documentation_codefixer_ai_en.md
// §2.1): a structured, non-blocking console log of method/path/userId/
// timestamp is sufficient for this phase — no dedicated audit table exists
// beyond db/migrations/001_init.sql's schema (CONTRACT.md §7 lists exactly
// which tables exist; there is no `audit_log` table to write to). Emitting
// via setImmediate keeps this off the request's synchronous path so it never
// adds latency to the response.
export function auditLog(req: Request, res: Response, next: NextFunction): void {
  const startedAt = Date.now();

  res.on('finish', () => {
    setImmediate(() => {
      const entry = {
        event: 'audit',
        method: req.method,
        path: req.originalUrl,
        userId: req.user?.sub ?? null,
        statusCode: res.statusCode,
        durationMs: Date.now() - startedAt,
        timestamp: new Date().toISOString(),
      };
      // eslint-disable-next-line no-console
      console.log(JSON.stringify(entry));
    });
  });

  next();
}
