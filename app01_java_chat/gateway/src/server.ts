import cors from 'cors';
import express from 'express';
import { config } from './config';
import { authRouter } from './routes/auth';
import { chatRouter } from './routes/chat';
import { healthRouter } from './routes/health';
import { auditLog } from './middleware/audit';

const app = express();

app.use(cors());
app.use(express.json({ limit: '2mb' }));

// Health check is intentionally mounted before the audit middleware — it's
// polled frequently by container orchestration and isn't user-facing traffic
// worth auditing.
app.use(healthRouter);

app.use(auditLog);
app.use(authRouter);
app.use(chatRouter);

// Fallback 404 for anything outside the contract.
app.use((_req, res) => {
  res.status(404).json({ error: 'not_found' });
});

app.listen(config.gatewayPort, () => {
  // eslint-disable-next-line no-console
  console.log(
    JSON.stringify({
      event: 'gateway_started',
      port: config.gatewayPort,
      orchestratorUrl: config.orchestratorUrl,
      timestamp: new Date().toISOString(),
    })
  );
});
