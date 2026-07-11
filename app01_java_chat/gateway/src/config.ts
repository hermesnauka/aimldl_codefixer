// Typed env var loading with fail-fast validation. Import this module first
// (server.ts does) so a misconfigured deployment throws at startup instead of
// failing silently on the first request that needs the missing value.

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value || value.trim() === '') {
    throw new Error(
      `Missing required environment variable: ${name}. Set it before starting the gateway (see .env.example).`
    );
  }
  return value;
}

export interface Config {
  gatewayPort: number;
  databaseUrl: string;
  jwtSecret: string;
  orchestratorUrl: string;
}

function loadConfig(): Config {
  const jwtSecret = requireEnv('JWT_SECRET');
  const databaseUrl = requireEnv('DATABASE_URL');
  const orchestratorUrl = requireEnv('ORCHESTRATOR_URL');

  const rawPort = process.env.GATEWAY_PORT ?? '4000';
  const gatewayPort = Number(rawPort);
  if (!Number.isInteger(gatewayPort) || gatewayPort <= 0) {
    throw new Error(`GATEWAY_PORT must be a positive integer, got: "${rawPort}"`);
  }

  return {
    gatewayPort,
    databaseUrl,
    jwtSecret,
    orchestratorUrl: orchestratorUrl.replace(/\/+$/, ''), // normalize trailing slash
  };
}

export const config: Config = loadConfig();
