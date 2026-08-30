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

# --ignore-scripts: postinstall runs `nuxt prepare`, which needs the app source
# to generate correct types/aliases. Source isn't copied yet at this layer (kept
# separate for cache reuse), so running it here would bake a stale .nuxt dir and
# break "@/..." import resolution during the later build.
RUN --mount=type=cache,id=pnpm,target=/pnpm/store,uid=1000,gid=1000 pnpm install --frozen-lockfile --ignore-scripts

COPY --chown=node:node . .

RUN pnpm run generate


FROM nginx:alpine AS pro

COPY nginx.conf.template /etc/nginx/templates/default.conf.template

COPY --from=build /app/.output/public /usr/share/nginx/html
