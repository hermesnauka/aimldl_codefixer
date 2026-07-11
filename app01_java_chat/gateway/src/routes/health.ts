import { Router } from 'express';

export const healthRouter = Router();

// CONTRACT.md §1: GET /health -> {"status":"UP"}. Deliberately unauthenticated
// (used by container orchestration / docker-compose healthchecks).
healthRouter.get('/health', (_req, res) => {
  res.status(200).json({ status: 'UP' });
});
