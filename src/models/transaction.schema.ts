import { z } from 'zod';
import { TransactionType } from '@prisma/client';

export const createTransactionSchema = z.object({
  amount: z.number().positive(),
  type: z.nativeEnum(TransactionType),
  category: z.string().min(1),
  date: z.string().datetime(),
  notes: z.string().optional(),
});

export const updateTransactionSchema = z.object({
  amount: z.number().positive().optional(),
  type: z.nativeEnum(TransactionType).optional(),
  category: z.string().min(1).optional(),
  date: z.string().datetime().optional(),
  notes: z.string().nullable().optional(),
});

export const transactionQuerySchema = z.object({
  type: z.nativeEnum(TransactionType).optional(),
  category: z.string().optional(),
  from: z.string().datetime().optional(),
  to: z.string().datetime().optional(),
  page: z.coerce.number().int().min(1).optional().default(1),
  limit: z.coerce.number().int().min(1).max(100).optional().default(20),
});

export type CreateTransactionInput = z.infer<typeof createTransactionSchema>;
export type UpdateTransactionInput = z.infer<typeof updateTransactionSchema>;
export type TransactionQueryInput = z.infer<typeof transactionQuerySchema>;
