import { NextFunction, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import { config } from '../config';

export interface AuthTokenPayload {
  sub: string; // user id (uuid)
  username: string;
}

// Express's Request typing is augmented here so downstream handlers get a
// typed req.user without a cast at every call site.
declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthTokenPayload;
    }
  }
}

// CONTRACT.md §6: every route except /api/v1/auth/login and /health requires
// `Authorization: Bearer <token>`, verified here. 401 on anything missing or
// invalid — no silent fallback.
export function requireAuth(req: Request, res: Response, next: NextFunction): void {
  const header = req.header('authorization') ?? req.header('Authorization');
  if (!header || !header.startsWith('Bearer ')) {
    res.status(401).json({ error: 'invalid_credentials' });
    return;
  }

  const token = header.slice('Bearer '.length).trim();
  if (!token) {
    res.status(401).json({ error: 'invalid_credentials' });
    return;
  }

  try {
    const payload = jwt.verify(token, config.jwtSecret) as jwt.JwtPayload | string;
    if (typeof payload === 'string' || !payload.sub || typeof payload.username !== 'string') {
      res.status(401).json({ error: 'invalid_credentials' });
      return;
    }
    req.user = { sub: payload.sub, username: payload.username };
    next();
  } catch {
    res.status(401).json({ error: 'invalid_credentials' });
  }
}
