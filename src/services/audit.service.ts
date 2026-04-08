import { prisma as db } from '../config/prisma';

export class AuditService {
  /**
   * Log an action automatically.
   */
  async log(
    userId: string,
    action: string,
    resource: string,
    resourceId: string,
    metadata?: any
  ): Promise<void> {
    try {
      await db.auditLog.create({
        data: {
          userId,
          action,
          resource,
          resourceId,
          metadata: metadata || null,
        },
      });
    } catch (error) {
      // Don't throw errors for audit logging failure, but log them
      console.error('Failed to write audit log:', error);
    }
  }
}

export const auditService = new AuditService();
