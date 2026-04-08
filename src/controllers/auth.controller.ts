import { Request, Response, NextFunction } from 'express';
import * as authService from '../services/auth.service';
import { RegisterInput, LoginInput, RefreshTokenInput } from '../models/auth.schema';

/**
 * POST /auth/register
 * Creates a new user account and returns tokens.
 */
export async function register(
  req: Request<object, object, RegisterInput>,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const meta = {
      userAgent: req.headers['user-agent'],
      ipAddress: req.ip,
    };

    const { user, tokens } = await authService.register(req.body, meta);

    res.status(201).json({
      status: 'success',
      message: 'Account created successfully',
      data: {
        user,
        ...tokens,
      },
    });
  } catch (err) {
    next(err);
  }
}

/**
 * POST /auth/login
 * Authenticates a user and returns access + refresh tokens.
 */
export async function login(
  req: Request<object, object, LoginInput>,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const meta = {
      userAgent: req.headers['user-agent'],
      ipAddress: req.ip,
    };

    const { user, tokens } = await authService.login(req.body, meta);

    res.status(200).json({
      status: 'success',
      message: 'Login successful',
      data: {
        user,
        ...tokens,
      },
    });
  } catch (err) {
    next(err);
  }
}

/**
 * POST /auth/refresh
 * Issues a new access/refresh token pair using a valid refresh token.
 */
export async function refresh(
  req: Request<object, object, RefreshTokenInput>,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const meta = {
      userAgent: req.headers['user-agent'],
      ipAddress: req.ip,
    };

    const tokens = await authService.refreshTokens(req.body.refreshToken, meta);

    res.status(200).json({
      status: 'success',
      message: 'Tokens refreshed successfully',
      data: tokens,
    });
  } catch (err) {
    next(err);
  }
}

/**
 * POST /auth/logout
 * Revokes the provided refresh token session.
 */
export async function logout(
  req: Request<object, object, RefreshTokenInput>,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    await authService.logout(req.body.refreshToken);

    res.status(200).json({
      status: 'success',
      message: 'Logged out successfully',
    });
  } catch (err) {
    next(err);
  }
}

/**
 * GET /auth/me
 * Returns the authenticated user's profile from the JWT payload.
 * Requires requireAuth middleware.
 */
export function me(req: Request, res: Response): void {
  res.status(200).json({
    status: 'success',
    data: { user: req.user },
  });
}
