import { Request, Response, NextFunction } from 'express';
import { logger } from '../utils/logger';

/**
 * Handle 404 for unknown routes.
 */
export function notFoundHandler(req: Request, res: Response, next: NextFunction): void {
  const error = new Error(`Not Found - ${req.originalUrl}`);
  res.status(404);
  next(error);
}

/**
 * Global error handler.
 */
export function errorHandler(
  err: any,
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  let statusCode = res.statusCode !== 200 ? res.statusCode : 500;
  let message = err.message || 'Internal Server Error';
  let code = err.code || 'INTERNAL_ERROR';

  // Map Prisma errors
  if (err.name === 'PrismaClientKnownRequestError') {
    if (err.code === 'P2002') {
      statusCode = 409;
      message = 'A record with this value already exists (conflict).';
      code = 'CONFLICT';
    } else if (err.code === 'P2025') {
      statusCode = 404;
      message = 'Record not found.';
      code = 'NOT_FOUND';
    } else if (err.code === 'P2003') {
      statusCode = 400;
      message = 'Foreign key constraint failed.';
      code = 'BAD_REQUEST';
    }
  } else if (err.name === 'PrismaClientValidationError') {
    statusCode = 400;
    message = 'Database validation error.';
    code = 'BAD_REQUEST';
  } else if (err.status) {
    statusCode = err.status;
    code = statusCode === 404 ? 'NOT_FOUND' : statusCode === 403 ? 'FORBIDDEN' : statusCode === 401 ? 'UNAUTHORIZED' : statusCode === 400 ? 'BAD_REQUEST' : 'ERROR';
  }

  // Ensure 500 on unmapped unexpected errors
  if (statusCode < 400) {
    statusCode = 500;
  }

  // Log error using Pino
  logger.error({ err }, message);

  res.status(statusCode).json({
    success: false,
    error: {
      code,
      message,
      ...(process.env.NODE_ENV !== 'production' && { stack: err.stack }),
    },
  });
}
