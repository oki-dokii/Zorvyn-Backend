import { Role, User } from '@prisma/client';

/**
 * Public-safe user object — strips passwordHash before returning to clients.
 */
export type PublicUser = Omit<User, 'passwordHash'>;

/**
 * The payload embedded in JWT access tokens.
 */
export interface JwtAccessPayload {
  sub: string;   // user id
  email: string;
  role: Role;
  iat?: number;
  exp?: number;
}

/**
 * The payload embedded in JWT refresh tokens.
 */
export interface JwtRefreshPayload {
  sub: string;      // user id
  sessionId: string;
  iat?: number;
  exp?: number;
}

/**
 * Shape returned by the auth service on successful login/register.
 */
export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number; // seconds until access token expires
}
