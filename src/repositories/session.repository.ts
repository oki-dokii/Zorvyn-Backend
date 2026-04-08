import { Prisma, Session } from '@prisma/client';
import { prisma } from '../config/prisma';

/**
 * Repository layer for Session table — manages refresh-token sessions.
 */

/**
 * Create a new session record associated with a user.
 * @param data - Session creation fields including userId, refreshToken, and expiresAt.
 * @returns The newly created Session.
 */
export async function createSession(data: Prisma.SessionCreateInput): Promise<Session> {
  return prisma.session.create({ data });
}

/**
 * Find a session by its refresh token.
 * @param refreshToken - The hashed or raw refresh token to look up.
 * @returns The matching Session (with associated user) or null.
 */
export async function findSessionByToken(refreshToken: string): Promise<Session | null> {
  return prisma.session.findUnique({ where: { refreshToken } });
}

/**
 * Delete a session by its ID (logout / token rotation).
 * @param id - The session's CUID.
 */
export async function deleteSession(id: string): Promise<void> {
  await prisma.session.delete({ where: { id } }).catch(() => {
    // Silently ignore if already deleted (idempotent logout)
  });
}

/**
 * Delete all sessions for a given user (e.g. force logout all devices).
 * @param userId - The user's CUID.
 * @returns The number of deleted sessions.
 */
export async function deleteAllUserSessions(userId: string): Promise<number> {
  const result = await prisma.session.deleteMany({ where: { userId } });
  return result.count;
}

/**
 * Remove all expired sessions from the database.
 * Intended to be called from a scheduled cleanup job.
 * @returns The number of pruned sessions.
 */
export async function pruneExpiredSessions(): Promise<number> {
  const result = await prisma.session.deleteMany({
    where: { expiresAt: { lt: new Date() } },
  });
  return result.count;
}
