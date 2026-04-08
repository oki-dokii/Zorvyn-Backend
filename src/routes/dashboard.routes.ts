import { Router } from 'express';
import { requireAuth, requireRole } from '../middlewares/auth.middleware';
import {
  getSummary,
  getCategoryBreakdown,
  getMonthlyTrend,
  getRecentActivity,
  getTopCategories,
} from '../controllers/dashboard.controller';

const router = Router();

// All routes are protected by default
router.use(requireAuth);

/**
 * @swagger
 * /api/dashboard/summary:
 *   get:
 *     summary: Get dashboard summary
 *     tags: [Dashboard]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Success
 */
// VIEWER can access only these
router.get('/summary', getSummary);

/**
 * @swagger
 * /api/dashboard/recent-activity:
 *   get:
 *     summary: Get recent transactions
 *     tags: [Dashboard]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Success
 */
router.get('/recent-activity', getRecentActivity);

/**
 * @swagger
 * /api/dashboard/category-breakdown:
 *   get:
 *     summary: Get category breakdown
 *     tags: [Dashboard]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Success
 */
// ANALYST and ADMIN can access everything
router.get(
  '/category-breakdown',
  requireRole('ADMIN', 'ANALYST'),
  getCategoryBreakdown
);

/**
 * @swagger
 * /api/dashboard/monthly-trend:
 *   get:
 *     summary: Get monthly trend
 *     tags: [Dashboard]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Success
 */
router.get(
  '/monthly-trend',
  requireRole('ADMIN', 'ANALYST'),
  getMonthlyTrend
);

/**
 * @swagger
 * /api/dashboard/top-categories:
 *   get:
 *     summary: Get top categories
 *     tags: [Dashboard]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Success
 */
router.get(
  '/top-categories',
  requireRole('ADMIN', 'ANALYST'),
  getTopCategories
);

export default router;
