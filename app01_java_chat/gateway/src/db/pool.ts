import { Pool } from 'pg';
import { config } from '../config';

// Single shared connection pool for the gateway's own narrowly-scoped
// DATABASE_URL (CONTRACT.md §7) — writes session/chat_messages rows here;
// llm_call_logs/code_execution_logs/failover_incidents are the Orchestrator's
// responsibility, not written by the gateway.
export const pool = new Pool({
  connectionString: config.databaseUrl,
});

pool.on('error', (err) => {
  // Unexpected errors on idle clients (e.g. connection dropped by Postgres)
  // must not crash the process — log and let the pool recover the next
  // checkout.
  // eslint-disable-next-line no-console
  console.error(JSON.stringify({ event: 'pg_pool_error', message: err.message, timestamp: new Date().toISOString() }));
});
