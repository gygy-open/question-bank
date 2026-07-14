FROM node:22-trixie-slim AS base

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@9.15.1 --activate

WORKDIR /app


# PWA

FROM base AS build

RUN mkdir -p /pnpm && chown -R node:node /app /pnpm

COPY --chown=node:node pnpm-lock.yaml package.json .

USER node

RUN --mount=type=cache,id=pnpm,target=/pnpm/store,uid=1000,gid=1000 pnpm install --frozen-lockfile

COPY --chown=node:node . .

RUN pnpm run generate


FROM nginx:alpine AS pro

COPY nginx.conf.template /etc/nginx/templates/default.conf.template

COPY --from=build /app/.output/public /usr/share/nginx/html
