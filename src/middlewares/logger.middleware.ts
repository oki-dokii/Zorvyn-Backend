import pinoHttp from 'pino-http';
import { logger } from '../utils/logger';
import { Request, Response } from 'express';

export const requestLogger = pinoHttp({
  logger,
  customLogLevel: function (req, res, err) {
    if (res.statusCode >= 400 && res.statusCode < 500) {
      return 'warn';
    } else if (res.statusCode >= 500 || err) {
      return 'error';
    } else if (res.statusCode >= 300 && res.statusCode < 400) {
      return 'silent';
    }
    return 'info';
  },
  customProps: function (req, res) {
    const expressReq = req as unknown as Request;
    // Log the user ID if authenticated
    return {
      userId: expressReq.user?.sub,
    };
  },
});
