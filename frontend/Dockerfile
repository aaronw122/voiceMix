# Build the Vite app with Bun, serve the static output with nginx.
FROM oven/bun:1.2-alpine AS build
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
# Baked at build time (Vite inlines VITE_* into the bundle). CI can override.
ARG VITE_API_BASE_URL=https://voiceapi.awill.co
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN bun run build

FROM nginx:1.31-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
