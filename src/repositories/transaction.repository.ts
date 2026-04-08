import { PrismaClient, Transaction, Prisma, Role } from '@prisma/client';
import { prisma as db } from '../config/prisma';

export interface PaginationMeta {
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

export interface PaginatedResult<T> {
  data: T[];
  meta: PaginationMeta;
}

export class TransactionRepository {
  async create(userId: string, data: Prisma.TransactionCreateWithoutUserInput): Promise<Transaction> {
    return db.transaction.create({
      data: {
        ...data,
        userId,
      },
    });
  }

  async findAll(
    userId: string,
    role: Role,
    filters: {
      type?: Prisma.EnumTransactionTypeFilter | Prisma.TransactionType;
      category?: string;
      from?: string;
      to?: string;
    },
    page: number,
    limit: number,
  ): Promise<PaginatedResult<Transaction>> {
    const where: Prisma.TransactionWhereInput = {
      deletedAt: null,
    };

    if (role !== Role.ADMIN) {
      where.userId = userId;
    }

    if (filters.type) where.type = filters.type;
    if (filters.category) where.category = filters.category;
    if (filters.from || filters.to) {
      where.date = {};
      if (filters.from) where.date.gte = new Date(filters.from);
      if (filters.to) where.date.lte = new Date(filters.to);
    }

    const skip = (page - 1) * limit;

    const [total, data] = await Promise.all([
      db.transaction.count({ where }),
      db.transaction.findMany({
        where,
        skip,
        take: limit,
        orderBy: { date: 'desc' },
      }),
    ]);

    return {
      data,
      meta: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    };
  }

  async findById(id: string): Promise<Transaction | null> {
    return db.transaction.findUnique({
      where: { id, deletedAt: null },
    });
  }

  async update(id: string, data: Prisma.TransactionUpdateInput): Promise<Transaction> {
    return db.transaction.update({
      where: { id },
      data,
    });
  }

  async softDelete(id: string): Promise<Transaction> {
    return db.transaction.update({
      where: { id },
      data: { deletedAt: new Date() },
    });
  }
}
