FROM oven/bun:1 AS builder
WORKDIR /app
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile
COPY . .
# Build-arg → env var. Vite reads any VITE_* env var at compile time and
# inlines it into the bundle as ``import.meta.env.VITE_BUILD_SHA``. Used by
# the Settings → About panel to show what's actually deployed.
ARG VITE_BUILD_SHA=dev
ENV VITE_BUILD_SHA=${VITE_BUILD_SHA}
RUN bun run build

FROM nginx:alpine AS runner
RUN rm /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/public /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

ENV BACKEND_URL=http://backend:8000
EXPOSE 3000
