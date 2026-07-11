import bcrypt from 'bcrypt';
import { Router } from 'express';
import jwt from 'jsonwebtoken';
import { pool } from '../db/pool';
import { config } from '../config';

export const authRouter = Router();

interface LoginRequestBody {
  username?: unknown;
  password?: unknown;
}

// CONTRACT.md §1 POST /api/v1/auth/login
authRouter.post('/api/v1/auth/login', async (req, res) => {
  const body = req.body as LoginRequestBody;
  const username = typeof body.username === 'string' ? body.username : null;
  const password = typeof body.password === 'string' ? body.password : null;

  if (!username || !password) {
    res.status(401).json({ error: 'invalid_credentials' });
    return;
  }

  try {
    const result = await pool.query<{ id: string; username: string; password_hash: string }>(
      'SELECT id, username, password_hash FROM users WHERE username = $1',
      [username]
    );

    const user = result.rows[0];
    if (!user) {
      res.status(401).json({ error: 'invalid_credentials' });
      return;
    }

    const passwordMatches = await bcrypt.compare(password, user.password_hash);
    if (!passwordMatches) {
      res.status(401).json({ error: 'invalid_credentials' });
      return;
    }

    const token = jwt.sign({ sub: user.id, username: user.username }, config.jwtSecret, {
      algorithm: 'HS256',
      expiresIn: '12h',
    });

    res.status(200).json({ token, username: user.username });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(JSON.stringify({ event: 'login_error', message: (err as Error).message, timestamp: new Date().toISOString() }));
    res.status(401).json({ error: 'invalid_credentials' });
  }
});
