import { PrismaClient, Role } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

const SALT_ROUNDS = 12;

interface SeedUser {
  email: string;
  password: string;
  role: Role;
}

const seedUsers: SeedUser[] = [
  {
    email: 'admin@finance.dev',
    password: 'Admin@123!',
    role: Role.ADMIN,
  },
  {
    email: 'analyst@finance.dev',
    password: 'Analyst@123!',
    role: Role.ANALYST,
  },
  {
    email: 'viewer@finance.dev',
    password: 'Viewer@123!',
    role: Role.VIEWER,
  },
];

/**
 * Seeds the database with one user per role for testing & development.
 * Existing users (matched by email) are updated rather than duplicated.
 */
async function main(): Promise<void> {
  console.log('🌱 Starting database seed...\n');

  for (const seedUser of seedUsers) {
    const passwordHash = await bcrypt.hash(seedUser.password, SALT_ROUNDS);

    const user = await prisma.user.upsert({
      where: { email: seedUser.email },
      update: {
        passwordHash,
        role: seedUser.role,
        isActive: true,
      },
      create: {
        email: seedUser.email,
        passwordHash,
        role: seedUser.role,
        isActive: true,
      },
    });

    console.log(`✅ Seeded [${user.role.padEnd(8)}] → ${user.email}`);
    console.log(`   Password: ${seedUser.password}`);
    console.log(`   ID:       ${user.id}\n`);
  }

  console.log('✨ Seed completed successfully.');
}

main()
  .catch((err) => {
    console.error('❌ Seed failed:', err);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
