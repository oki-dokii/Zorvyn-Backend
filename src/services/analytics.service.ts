import { Role, TransactionType, Prisma } from '@prisma/client';
import { prisma as db } from '../config/prisma';
import { appCache } from '../utils/cache.service';

export interface SummaryData {
  totalIncome: number;
  totalExpenses: number;
  netBalance: number;
  transactionCount: number;
}

export interface CategoryBreakdown {
  category: string;
  total: number;
  percentage: number;
  count: number;
}

export interface MonthlyTrend {
  month: number; // 1-12
  income: number;
  expenses: number;
  net: number;
}

export interface RecentActivity {
  id: string;
  amount: number;
  type: TransactionType;
  category: string;
  date: Date;
  notes: string | null;
  runningBalance: number;
}

export interface TopCategory {
  category: string;
  total: number;
}

export class AnalyticsService {
  /**
   * Helper to build base where clause scoped to role.
   */
  private getBaseWhere(userId: string, role: Role): Prisma.TransactionWhereInput {
    // Admin gets all active records, others get their own active records
    const where: Prisma.TransactionWhereInput = {
      deletedAt: null,
    };
    if (role !== Role.ADMIN) {
      where.userId = userId;
    }
    return where;
  }

  async getSummary(userId: string, role: Role): Promise<SummaryData> {
    const cacheKey = `summary:${role}:${role !== Role.ADMIN ? userId : 'all'}`;
    const cached = appCache.get<SummaryData>(cacheKey);
    if (cached) {
      return cached;
    }

    const where = this.getBaseWhere(userId, role);

    const [incomeAgg, expenseAgg, count] = await Promise.all([
      db.transaction.aggregate({
        where: { ...where, type: TransactionType.INCOME },
        _sum: { amount: true },
      }),
      db.transaction.aggregate({
        where: { ...where, type: TransactionType.EXPENSE },
        _sum: { amount: true },
      }),
      db.transaction.count({ where }),
    ]);

    const totalIncome = Number(incomeAgg._sum.amount || 0);
    const totalExpenses = Number(expenseAgg._sum.amount || 0);

    const result: SummaryData = {
      totalIncome,
      totalExpenses,
      netBalance: totalIncome - totalExpenses,
      transactionCount: count,
    };

    appCache.set(cacheKey, result, 60); // cache for 60 seconds
    return result;
  }

  async getCategoryBreakdown(
    userId: string,
    role: Role,
    type?: TransactionType
  ): Promise<CategoryBreakdown[]> {
    const where = this.getBaseWhere(userId, role);
    if (type) {
      where.type = type;
    }

    const [groups, totalResult] = await Promise.all([
      db.transaction.groupBy({
        by: ['category'],
        where,
        _sum: { amount: true },
        _count: { id: true },
        orderBy: {
          _sum: {
            amount: 'desc',
          },
        },
      }),
      db.transaction.aggregate({
        where,
        _sum: { amount: true },
      }),
    ]);

    const totalAmount = Number(totalResult._sum.amount || 0);

    return groups.map((g) => {
      const categoryTotal = Number(g._sum.amount || 0);
      return {
        category: g.category,
        total: categoryTotal,
        percentage: totalAmount > 0 ? (categoryTotal / totalAmount) * 100 : 0,
        count: g._count.id,
      };
    });
  }

  async getMonthlyTrend(userId: string, role: Role, year: number): Promise<MonthlyTrend[]> {
    // Generate dates for the specific year
    const startOfYear = new Date(`${year}-01-01T00:00:00.000Z`);
    const endOfYear = new Date(`${year + 1}-01-01T00:00:00.000Z`);

    const where = this.getBaseWhere(userId, role);
    where.date = {
      gte: startOfYear,
      lt: endOfYear,
    };

    // We fetch everything for that year, and accumulate in memory since Prisma doesn't have an EXTRACT(MONTH) raw aggregation method directly mapped that's database independent.
    // Alternatively, using raw queries:
    
    let rawData: any[];
    if (role !== Role.ADMIN) {
      rawData = await db.$queryRaw`
        SELECT 
          EXTRACT(MONTH FROM date)::int AS month,
          type,
          SUM(amount) AS total
        FROM transactions
        WHERE "deletedAt" IS NULL 
          AND "userId" = ${userId}
          AND date >= ${startOfYear} 
          AND date < ${endOfYear}
        GROUP BY EXTRACT(MONTH FROM date), type
      `;
    } else {
      rawData = await db.$queryRaw`
        SELECT 
          EXTRACT(MONTH FROM date)::int AS month,
          type,
          SUM(amount) AS total
        FROM transactions
        WHERE "deletedAt" IS NULL 
          AND date >= ${startOfYear} 
          AND date < ${endOfYear}
        GROUP BY EXTRACT(MONTH FROM date), type
      `;
    }

    // Initialize 12 months array
    const months: MonthlyTrend[] = Array.from({ length: 12 }).map((_, i) => ({
      month: i + 1,
      income: 0,
      expenses: 0,
      net: 0,
    }));

    for (const row of rawData) {
      // Month could be extracted starting from 1
      const monthIndex = row.month - 1;
      const amount = Number(row.total || 0);
      
      if (row.type === 'INCOME') {
        months[monthIndex].income += amount;
      } else {
        months[monthIndex].expenses += amount;
      }
    }

    // Calculate net
    for (const m of months) {
      m.net = m.income - m.expenses;
    }

    return months;
  }

  async getRecentActivity(userId: string, role: Role, limit: number): Promise<RecentActivity[]> {
    const where = this.getBaseWhere(userId, role);

    // Fetch the transactions descending
    const transactions = await db.transaction.findMany({
      where,
      orderBy: { date: 'desc' },
      take: limit,
    });

    // To calculate running balance, we need the total income and expenses up to each transaction if we wanted to be perfectly precise from beginning of time, but a common approach for simple "recent activity with running balance" is to calculate the balance *as of that day* or backwards from the current balance.
    // Let's get the current total balance first to calculate backwards.
    const currentSummary = await this.getSummary(userId, role);
    let runningBalance = currentSummary.netBalance;

    const results: RecentActivity[] = [];

    // Assuming transactions are strictly ordered by date descending
    for (const t of transactions) {
      results.push({
        id: t.id,
        amount: Number(t.amount),
        type: t.type,
        category: t.category,
        date: t.date,
        notes: t.notes,
        runningBalance: runningBalance,
      });

      // Rollback the balance for the previous row
      if (t.type === 'INCOME') {
        runningBalance -= Number(t.amount);
      } else {
        runningBalance += Number(t.amount);
      }
    }

    return results;
  }

  async getTopCategories(userId: string, role: Role, limit: number): Promise<TopCategory[]> {
    const where = this.getBaseWhere(userId, role);
    where.type = TransactionType.EXPENSE; // usually "top categories" implies spending

    const groups = await db.transaction.groupBy({
      by: ['category'],
      where,
      _sum: { amount: true },
      orderBy: {
        _sum: {
          amount: 'desc',
        },
      },
      take: limit,
    });

    return groups.map((g) => ({
      category: g.category,
      total: Number(g._sum.amount || 0),
    }));
  }
}
