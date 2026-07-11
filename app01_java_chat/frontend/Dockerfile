# --- Build stage -----------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
# VITE_GATEWAY_URL is baked into the static bundle at build time (Vite env
# vars are compile-time, not runtime) — override via --build-arg if the
# Gateway isn't reachable at the default http://localhost:4000.
ARG VITE_GATEWAY_URL=http://localhost:4000
ENV VITE_GATEWAY_URL=$VITE_GATEWAY_URL
RUN npm run build

# --- Serve stage -------------------------------------------------------------
FROM nginx:1.27-alpine AS serve
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
