import { z } from 'zod';

/**
 * Zod schema for POST /auth/register
 */
export const registerSchema = z.object({
  email: z
    .string('Email is required')
    .email('Must be a valid email address')
    .toLowerCase()
    .trim(),
  password: z
    .string('Password is required')
    .min(8, 'Password must be at least 8 characters')
    .max(72, 'Password must be at most 72 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[a-z]/, 'Password must contain at least one lowercase letter')
    .regex(/[0-9]/, 'Password must contain at least one number')
    .regex(/[^A-Za-z0-9]/, 'Password must contain at least one special character'),
  role: z.enum(['VIEWER', 'ANALYST', 'ADMIN']).optional().default('VIEWER'),
});

/**
 * Zod schema for POST /auth/login
 */
export const loginSchema = z.object({
  email: z
    .string('Email is required')
    .email('Must be a valid email address')
    .toLowerCase()
    .trim(),
  password: z.string('Password is required').min(1, 'Password is required'),
});

/**
 * Zod schema for POST /auth/refresh
 */
export const refreshTokenSchema = z.object({
  refreshToken: z
    .string('Refresh token is required')
    .min(1, 'Refresh token is required'),
});

export type RegisterInput = z.infer<typeof registerSchema>;
export type LoginInput = z.infer<typeof loginSchema>;
export type RefreshTokenInput = z.infer<typeof refreshTokenSchema>;
