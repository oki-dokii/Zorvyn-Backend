import { Request, Response, NextFunction } from 'express';
import { Role } from '@prisma/client';
import { verifyAccessToken } from '../utils/jwt.utils';
import { findUserById } from '../repositories/user.repository';
import { JwtAccessPayload } from '../models/user.types';

// Extend the Express Request type to include the authenticated user
declare global {
  namespace Express {
    interface Request {
      user?: JwtAccessPayload & { isActive: boolean };
    }
  }
}

/**
 * Middleware that validates the Bearer JWT in the Authorization header.
 * On success, attaches the decoded payload to `req.user`.
 * On failure, responds with 401 Unauthorized.
 *
 * Usage: router.get('/protected', requireAuth, handler)
 */
export async function requireAuth(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({
      status: 'error',
      message: 'Authorization header missing or malformed. Expected: Bearer <token>',
    });
    return;
  }

  const token = authHeader.slice(7); // Strip "Bearer " prefix

  try {
    const payload = verifyAccessToken(token);

    // Optional: verify user still exists and is active
    const user = await findUserById(payload.sub);

    if (!user) {
      res.status(401).json({ status: 'error', message: 'User no longer exists' });
      return;
    }

    if (!user.isActive) {
      res.status(401).json({ status: 'error', message: 'Account is deactivated' });
      return;
    }

    req.user = { ...payload, isActive: user.isActive };
    next();
  } catch (err) {
    if (err instanceof Error) {
      if (err.name === 'TokenExpiredError') {
        res.status(401).json({ status: 'error', message: 'Access token expired' });
        return;
      }
      if (err.name === 'JsonWebTokenError') {
        res.status(401).json({ status: 'error', message: 'Invalid access token' });
        return;
      }
    }
    next(err);
  }
}

/**
 * Middleware factory for role-based access control (RBAC).
 * Must be used AFTER `requireAuth`.
 *
 * @param roles - One or more roles that are allowed access.
 * @returns Middleware that blocks requests from users without the required role.
 *
 * @example
 * router.delete('/users/:id', requireAuth, requireRole('ADMIN'), handler);
 * router.get('/reports', requireAuth, requireRole('ANALYST', 'ADMIN'), handler);
 */
export function requireRole(...roles: Role[]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ status: 'error', message: 'Not authenticated' });
      return;
    }

    if (!roles.includes(req.user.role as Role)) {
      res.status(403).json({
        status: 'error',
        message: `Access denied. Required role(s): ${roles.join(', ')}. Your role: ${req.user.role}`,
      });
      return;
    }

    next();
  };
}
