import { Request, Response, NextFunction } from 'express';
import { ZodSchema, ZodError } from 'zod';

/**
 * Middleware factory that validates `req.body` against a Zod schema.
 * On failure, responds with 422 Unprocessable Entity and field-level error details.
 *
 * @param schema - The Zod schema to validate against.
 * @returns Express middleware that parses & attaches the validated body.
 *
 * @example
 * router.post('/register', validate(registerSchema), authController.register);
 */
export function validate<T>(schema: ZodSchema<T>) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const result = schema.safeParse(req.body);

    if (!result.success) {
      const errors = formatZodErrors(result.error);
      res.status(422).json({
        status: 'error',
        message: 'Validation failed',
        errors,
      });
      return;
    }

    // Replace req.body with the coerced, parsed data
    req.body = result.data;
    next();
  };
}

/**
 * Middleware factory that validates `req.query` against a Zod schema.
 */
export function validateQuery<T>(schema: ZodSchema<T>) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const result = schema.safeParse(req.query);

    if (!result.success) {
      const errors = formatZodErrors(result.error);
      res.status(422).json({
        status: 'error',
        message: 'Query validation failed',
        errors,
      });
      return;
    }

    // Replace req.query with the coerced, parsed data
    req.query = result.data as any;
    next();
  };
}

/**
 * Transforms a ZodError into a flat, field-keyed error map for easy client consumption.
 * @param error - The ZodError instance from a failed safeParse.
 * @returns An object mapping each field path to an array of error messages.
 */
function formatZodErrors(error: ZodError): Record<string, string[]> {
  const fieldErrors: Record<string, string[]> = {};

  for (const issue of error.issues) {
    const path = issue.path.join('.');
    const key = path || '_root';

    if (!fieldErrors[key]) {
      fieldErrors[key] = [];
    }
    fieldErrors[key].push(issue.message);
  }

  return fieldErrors;
}
