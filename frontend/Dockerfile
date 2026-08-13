# ---- Build stage ----
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines VITE_* variables into the bundle at build time, not at
# container start — they have to arrive as build args, not just runtime
# env vars (see docker-compose.yml's build.args for this service). No
# API key needed here: the web app authenticates via individual user
# login (JWT), not a build-time secret — see src/services/api.js.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---- Serve stage ----
FROM nginx:alpine

# Re-declared: ARGs don't cross build stages. Same default as the build
# stage above, so the CSP's connect-src always matches whatever origin
# the JS bundle was actually built to call (see nginx.conf's comment).
ARG VITE_API_BASE_URL=http://localhost:8000

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i "s#__API_BASE_ORIGIN__#${VITE_API_BASE_URL}#g" /etc/nginx/conf.d/default.conf

EXPOSE 80
