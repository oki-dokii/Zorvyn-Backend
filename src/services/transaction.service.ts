import { Prisma, Role, Transaction } from '@prisma/client';
import { TransactionRepository, PaginatedResult } from '../repositories/transaction.repository';
import { CreateTransactionInput, UpdateTransactionInput, TransactionQueryInput } from '../models/transaction.schema';
import { auditService } from './audit.service';

export class TransactionService {
  private repo = new TransactionRepository();

  async createTransaction(
    userId: string,
    role: Role,
    data: CreateTransactionInput
  ): Promise<Transaction> {
    if (role !== Role.ADMIN && role !== Role.ANALYST) {
      throw { status: 403, message: 'Forbidden. Only ADMIN and ANALYST can create transactions.' };
    }
    const result = await this.repo.create(userId, {
      amount: data.amount,
      type: data.type,
      category: data.category,
      date: new Date(data.date),
      notes: data.notes,
    });

    await auditService.log(userId, 'CREATE', 'Transaction', result.id, data);
    return result;
  }

  async getTransactions(
    userId: string,
    role: Role,
    query: TransactionQueryInput
  ): Promise<PaginatedResult<Transaction>> {
    return this.repo.findAll(
      userId,
      role,
      {
        type: query.type,
        category: query.category,
        from: query.from,
        to: query.to,
      },
      query.page,
      query.limit
    );
  }

  async getTransactionById(
    userId: string,
    role: Role,
    transactionId: string
  ): Promise<Transaction> {
    const transaction = await this.repo.findById(transactionId);

    if (!transaction) {
      throw { status: 404, message: 'Transaction not found or has been deleted.' };
    }

    if (role !== Role.ADMIN && transaction.userId !== userId) {
      throw { status: 403, message: 'Forbidden. You do not have access to this transaction.' };
    }

    return transaction;
  }

  async updateTransaction(
    userId: string,
    role: Role,
    transactionId: string,
    data: UpdateTransactionInput
  ): Promise<Transaction> {
    if (role !== Role.ADMIN && role !== Role.ANALYST) {
      throw { status: 403, message: 'Forbidden. Only ADMIN and ANALYST can update transactions.' };
    }

    const transaction = await this.repo.findById(transactionId);
    if (!transaction) {
      throw { status: 404, message: 'Transaction not found or has been deleted.' };
    }

    if (role !== Role.ADMIN && transaction.userId !== userId) {
      throw { status: 403, message: 'Forbidden. You do not have access to clarify this transaction.' };
    }

    const updateData: Prisma.TransactionUpdateInput = {};
    if (data.amount !== undefined) updateData.amount = data.amount;
    if (data.type !== undefined) updateData.type = data.type;
    if (data.category !== undefined) updateData.category = data.category;
    if (data.date !== undefined) updateData.date = new Date(data.date);
    if (data.notes !== undefined) updateData.notes = data.notes;

    const result = await this.repo.update(transactionId, updateData);
    await auditService.log(userId, 'UPDATE', 'Transaction', transactionId, updateData);
    return result;
  }

  async deleteTransaction(
    userId: string,
    role: Role,
    transactionId: string
  ): Promise<void> {
    if (role !== Role.ADMIN) {
      throw { status: 403, message: 'Forbidden. Only ADMIN can delete transactions.' };
    }

    const transaction = await this.repo.findById(transactionId);
    if (!transaction) {
      throw { status: 404, message: 'Transaction not found or already deleted.' };
    }

    await this.repo.softDelete(transactionId);
    await auditService.log(userId, 'DELETE', 'Transaction', transactionId);
  }
}
