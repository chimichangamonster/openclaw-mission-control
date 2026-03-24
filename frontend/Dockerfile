# syntax=docker/dockerfile:1

FROM oven/bun:1-alpine AS deps
WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM oven/bun:1-alpine AS builder
WORKDIR /app

# Need node for next build (Next.js requires Node runtime)
RUN apk add --no-cache nodejs

COPY --from=deps /app/node_modules ./node_modules
COPY . ./

# Allows configuring the API URL at build time.
ARG NEXT_PUBLIC_API_URL=auto
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ARG NEXT_PUBLIC_AUTH_MODE
ENV NEXT_PUBLIC_AUTH_MODE=${NEXT_PUBLIC_AUTH_MODE}
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}

RUN bun run build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ARG NEXT_PUBLIC_AUTH_MODE

# If provided at runtime, Next will expose NEXT_PUBLIC_* to the browser as well
# (but note some values may be baked at build time).
ENV NEXT_PUBLIC_API_URL=auto
ENV NEXT_PUBLIC_AUTH_MODE=${NEXT_PUBLIC_AUTH_MODE}

# Create non-root user before COPY so --chown can reference it.
# Using COPY --chown avoids a slow recursive chown on overlay2 (docker/for-linux#388).
RUN addgroup -S appgroup && adduser -S -G appgroup appuser \
  && chown appuser:appgroup /app

COPY --from=builder --chown=appuser:appgroup /app/.next ./.next
COPY --from=builder --chown=appuser:appgroup /app/public ./public
COPY --from=builder --chown=appuser:appgroup /app/package.json ./package.json
COPY --from=builder --chown=appuser:appgroup /app/node_modules ./node_modules
COPY --from=builder --chown=appuser:appgroup /app/next.config.ts ./next.config.ts

USER appuser

EXPOSE 3000

CMD ["node_modules/.bin/next", "start"]
