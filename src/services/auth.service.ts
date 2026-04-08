import bcrypt from 'bcryptjs';
import { Role } from '@prisma/client';
import { env } from '../config/env';
import { createError } from '../middlewares/error.middleware';
import { findUserByEmail, createUser, findUserById } from '../repositories/user.repository';
import {
  createSession,
  findSessionByToken,
  deleteSession,
} from '../repositories/session.repository';
import {
  signAccessToken,
  signRefreshToken,
  verifyRefreshToken,
  getAccessTokenExpirySeconds,
  getRefreshTokenExpiryDate,
} from '../utils/jwt.utils';
import { RegisterInput, LoginInput } from '../models/auth.schema';
import { AuthTokens, PublicUser } from '../models/user.types';

/**
 * Strip passwordHash before returning user data to controllers.
 */
function sanitizeUser(user: {
  id: string;
  email: string;
  passwordHash: string;
  role: Role;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}): PublicUser {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { passwordHash, ...publicUser } = user;
  return publicUser;
}

/**
 * Internal helper: create both access and refresh tokens for a user and persist the session.
 */
async function generateTokensAndSession(
  userId: string,
  email: string,
  role: Role,
  meta?: { userAgent?: string; ipAddress?: string },
): Promise<AuthTokens> {
  const expiresAt = getRefreshTokenExpiryDate();

  // Sign refresh token first (we need the sessionId for the payload)
  // We create the session with a placeholder, then sign
  const session = await createSession({
    user: { connect: { id: userId } },
    refreshToken: '__placeholder__',
    userAgent: meta?.userAgent,
    ipAddress: meta?.ipAddress,
    expiresAt,
  });

  const refreshToken = signRefreshToken({ sub: userId, sessionId: session.id });
  const accessToken = signAccessToken({ sub: userId, email, role });

  // Update session with real token
  await import('../config/prisma.js').then(({ prisma }) =>
    prisma.session.update({
      where: { id: session.id },
      data: { refreshToken },
    }),
  );

  return {
    accessToken,
    refreshToken,
    expiresIn: getAccessTokenExpirySeconds(),
  };
}

// ─── Service Functions ───────────────────────────────────────────────────────

/**
 * Register a new user account.
 * Validates uniqueness, hashes the password with bcrypt, and returns tokens.
 *
 * @param input - Validated registration body (email, password, role).
 * @param meta  - Optional request metadata for the session record.
 * @returns The sanitized public user and JWT token pair.
 * @throws 409 if the email is already registered.
 */
export async function register(
  input: RegisterInput,
  meta?: { userAgent?: string; ipAddress?: string },
): Promise<{ user: PublicUser; tokens: AuthTokens }> {
  const existing = await findUserByEmail(input.email);
  if (existing) {
    throw createError('An account with this email already exists', 409);
  }

  const passwordHash = await bcrypt.hash(input.password, env.BCRYPT_SALT_ROUNDS);

  const user = await createUser({
    email: input.email,
    passwordHash,
    role: input.role as Role,
  });

  const tokens = await generateTokensAndSession(user.id, user.email, user.role, meta);

  return { user: sanitizeUser(user), tokens };
}

/**
 * Authenticate an existing user with email + password.
 * Validates credentials, checks account status, and issues new tokens.
 *
 * @param input - Validated login body (email, password).
 * @param meta  - Optional request metadata for the session record.
 * @returns The sanitized public user and JWT token pair.
 * @throws 401 for invalid credentials or inactive accounts.
 */
export async function login(
  input: LoginInput,
  meta?: { userAgent?: string; ipAddress?: string },
): Promise<{ user: PublicUser; tokens: AuthTokens }> {
  const user = await findUserByEmail(input.email);

  // Use constant-time comparison even on "not found" to prevent user enumeration
  const passwordMatch = user
    ? await bcrypt.compare(input.password, user.passwordHash)
    : await bcrypt.compare(input.password, '$2b$12$invalidhashfortimingattackprevention');

  if (!user || !passwordMatch) {
    throw createError('Invalid email or password', 401);
  }

  if (!user.isActive) {
    throw createError('Your account has been deactivated. Contact support.', 401);
  }

  const tokens = await generateTokensAndSession(user.id, user.email, user.role, meta);

  return { user: sanitizeUser(user), tokens };
}

/**
 * Issue a new access + refresh token pair using a valid refresh token.
 * Implements refresh token rotation: the old session is deleted and a new one is created.
 *
 * @param refreshToken - The refresh token from the client.
 * @param meta         - Optional request metadata for the new session record.
 * @returns New access and refresh tokens.
 * @throws 401 if the token is invalid, expired, or the session doesn't exist.
 */
export async function refreshTokens(
  refreshToken: string,
  meta?: { userAgent?: string; ipAddress?: string },
): Promise<AuthTokens> {
  let payload;
  try {
    payload = verifyRefreshToken(refreshToken);
  } catch {
    throw createError('Invalid or expired refresh token', 401);
  }

  const session = await findSessionByToken(refreshToken);
  if (!session || session.expiresAt < new Date()) {
    // Token reuse detected or session expired — delete session
    if (session) await deleteSession(session.id);
    throw createError('Refresh token is invalid or has expired', 401);
  }

  const user = await findUserById(payload.sub);
  if (!user || !user.isActive) {
    await deleteSession(session.id);
    throw createError('User not found or account deactivated', 401);
  }

  // Token rotation: delete old session
  await deleteSession(session.id);

  // Issue new tokens
  return generateTokensAndSession(user.id, user.email, user.role, meta);
}

/**
 * Logout: invalidate the session associated with the given refresh token.
 * Silently succeeds if the session doesn't exist (idempotent).
 *
 * @param refreshToken - The refresh token to revoke.
 */
export async function logout(refreshToken: string): Promise<void> {
  const session = await findSessionByToken(refreshToken);
  if (session) {
    await deleteSession(session.id);
  }
}
