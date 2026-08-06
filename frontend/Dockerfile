# ---- Build stage ----
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines VITE_* variables into the bundle at build time, not at
# container start — they have to arrive as build args, not just runtime
# env vars (see docker-compose.yml's build.args for this service).
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_API_KEY=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_KEY=$VITE_API_KEY

RUN npm run build

# ---- Serve stage ----
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
