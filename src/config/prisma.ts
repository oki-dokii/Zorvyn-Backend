import { PrismaClient } from '@prisma/client';
import { env } from './env';

declare global {
  // eslint-disable-next-line no-var
  var __prisma: PrismaClient | undefined;
}

/**
 * Singleton Prisma client instance.
 * In development, the instance is cached on `globalThis` to survive hot-reloads.
 * In production a fresh instance is created per process.
 */
export const prisma: PrismaClient =
  env.NODE_ENV === 'production'
    ? new PrismaClient({
        log: ['warn', 'error'],
      })
    : (globalThis.__prisma ??= new PrismaClient({
        log: ['query', 'info', 'warn', 'error'],
      }));
