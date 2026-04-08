import jwt, { SignOptions } from 'jsonwebtoken';
import { env } from '../config/env';
import { JwtAccessPayload, JwtRefreshPayload } from '../models/user.types';

/**
 * Parse JWT expiry string (e.g. "15m", "7d") into seconds for the `expiresIn` response field.
 */
function parseExpiryToSeconds(expiry: string): number {
  const unit = expiry.slice(-1);
  const value = parseInt(expiry.slice(0, -1), 10);
  const map: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86400 };
  return (map[unit] ?? 60) * value;
}

/**
 * Sign a short-lived JWT access token.
 * @param payload - Claims to embed (userId, email, role).
 * @returns Signed JWT string.
 */
export function signAccessToken(payload: JwtAccessPayload): string {
  const options: SignOptions = {
    expiresIn: env.JWT_ACCESS_EXPIRES_IN as SignOptions['expiresIn'],
    algorithm: 'HS256',
  };
  return jwt.sign(payload, env.JWT_ACCESS_SECRET, options);
}

/**
 * Sign a long-lived JWT refresh token.
 * @param payload - Claims to embed (userId, sessionId).
 * @returns Signed JWT string.
 */
export function signRefreshToken(payload: JwtRefreshPayload): string {
  const options: SignOptions = {
    expiresIn: env.JWT_REFRESH_EXPIRES_IN as SignOptions['expiresIn'],
    algorithm: 'HS256',
  };
  return jwt.sign(payload, env.JWT_REFRESH_SECRET, options);
}

/**
 * Verify and decode a JWT access token.
 * @param token - Raw JWT string from the Authorization header.
 * @returns Decoded access payload.
 * @throws JsonWebTokenError or TokenExpiredError on invalid/expired tokens.
 */
export function verifyAccessToken(token: string): JwtAccessPayload {
  return jwt.verify(token, env.JWT_ACCESS_SECRET) as JwtAccessPayload;
}

/**
 * Verify and decode a JWT refresh token.
 * @param token - Raw JWT string from the request body.
 * @returns Decoded refresh payload.
 * @throws JsonWebTokenError or TokenExpiredError on invalid/expired tokens.
 */
export function verifyRefreshToken(token: string): JwtRefreshPayload {
  return jwt.verify(token, env.JWT_REFRESH_SECRET) as JwtRefreshPayload;
}

/**
 * Returns the number of seconds until the access token expires.
 * Useful for clients that need to know when to schedule a refresh.
 */
export function getAccessTokenExpirySeconds(): number {
  return parseExpiryToSeconds(env.JWT_ACCESS_EXPIRES_IN);
}

/**
 * Returns a Date object representing when a refresh token will expire.
 */
export function getRefreshTokenExpiryDate(): Date {
  const seconds = parseExpiryToSeconds(env.JWT_REFRESH_EXPIRES_IN);
  return new Date(Date.now() + seconds * 1000);
}
