import request from 'supertest';
import app from '../../src/app';
import { prisma as db } from '../../src/config/prisma';

describe('Transaction Integration Tests', () => {
  let token: string;
  let userId: string;

  beforeAll(async () => {
    // Clear models
    await db.auditLog.deleteMany();
    await db.transaction.deleteMany();
    await db.session.deleteMany();
    await db.user.deleteMany();

    // Register a user
    await request(app)
      .post('/auth/register')
      .send({
        email: 'test@example.com',
        password: 'Password123!',
        role: 'ADMIN',
      });

    // Login to get token
    const res = await request(app)
      .post('/auth/login')
      .send({
        email: 'test@example.com',
        password: 'Password123!',
      });

    token = res.body.data.accessToken;
    userId = res.body.data.user.id;
  });

  afterAll(async () => {
    await db.auditLog.deleteMany();
    await db.transaction.deleteMany();
    await db.session.deleteMany();
    await db.user.deleteMany();
    await db.$disconnect();
  });

  it('1. should login and return an access token', async () => {
    expect(token).toBeDefined();
    expect(typeof token).toBe('string');
  });

  let createdTransactionId: string;

  it('2. should create a new transaction using the token', async () => {
    const res = await request(app)
      .post('/api/transactions')
      .set('Authorization', `Bearer ${token}`)
      .send({
        amount: 100,
        type: 'INCOME',
        category: 'Freelance',
        date: new Date().toISOString(),
        notes: 'Test transaction',
      });

    expect(res.status).toBe(201);
    expect(res.body.success !== false).toBe(true); // Should be success
    expect(res.body.data.amount.toString()).toBe('100'); // Prisma decimal is stringified or JSON serialized depending on setup
    expect(res.body.data.type).toBe('INCOME');
    createdTransactionId = res.body.data.id;
  });

  it('3. should verify the transaction exists in the database', async () => {
    const transaction = await db.transaction.findUnique({
      where: { id: createdTransactionId },
    });

    expect(transaction).not.toBeNull();
    expect(Number(transaction!.amount)).toBe(100);
    expect(transaction!.category).toBe('Freelance');
  });
});
