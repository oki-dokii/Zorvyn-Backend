import { Router } from 'express';
import { requireAuth, requireRole } from '../middlewares/auth.middleware';
import { validate, validateQuery } from '../middlewares/validate.middleware';
import {
  createTransaction,
  getTransactions,
  getTransaction,
  updateTransaction,
  deleteTransaction,
} from '../controllers/transaction.controller';
import {
  createTransactionSchema,
  updateTransactionSchema,
  transactionQuerySchema,
} from '../models/transaction.schema';

const router = Router();

// All routes are protected
router.use(requireAuth);

/**
 * @swagger
 * /api/transactions:
 *   get:
 *     summary: Search and filter transactions
 *     tags: [Transactions]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Success
 */
router.get(
  '/',
  validateQuery(transactionQuerySchema),
  getTransactions
);

/**
 * @swagger
 * /api/transactions:
 *   post:
 *     summary: Create a transaction
 *     tags: [Transactions]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       201:
 *         description: Created
 */
router.post(
  '/',
  requireRole('ADMIN', 'ANALYST'),
  validate(createTransactionSchema),
  createTransaction
);

/**
 * @swagger
 * /api/transactions/{id}:
 *   get:
 *     summary: Get a single transaction
 *     tags: [Transactions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Success
 */
router.get(
  '/:id',
  getTransaction
);

/**
 * @swagger
 * /api/transactions/{id}:
 *   patch:
 *     summary: Update a transaction
 *     tags: [Transactions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Success
 */
router.patch(
  '/:id',
  requireRole('ADMIN', 'ANALYST'),
  validate(updateTransactionSchema),
  updateTransaction
);

/**
 * @swagger
 * /api/transactions/{id}:
 *   delete:
 *     summary: Soft delete a transaction
 *     tags: [Transactions]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *     responses:
 *       200:
 *         description: Success
 */
router.delete(
  '/:id',
  requireRole('ADMIN'),
  deleteTransaction
);

export default router;
