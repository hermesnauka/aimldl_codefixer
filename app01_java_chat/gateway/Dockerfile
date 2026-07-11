# --- Build stage ---
FROM node:22-slim AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# --- Runtime stage ---
FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

COPY --from=build /app/dist ./dist

# Matches docker-compose.yml's gateway service ("4000:4000") and
# .env.example's GATEWAY_PORT default — do not change without updating both.
ENV GATEWAY_PORT=4000
EXPOSE 4000

CMD ["node", "dist/server.js"]
