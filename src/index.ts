import app from './app';
import { env } from './config/env';
import { prisma } from './config/prisma';

async function bootstrap(): Promise<void> {
  try {
    // Verify database connectivity before accepting requests
    await prisma.$connect();
    console.log('✅ Database connected');

    const server = app.listen(env.PORT, () => {
      console.log(
        `🚀 Server running on port ${env.PORT} [${env.NODE_ENV.toUpperCase()}]`,
      );
      console.log(`   Health: http://localhost:${env.PORT}/health`);
      console.log(`   Auth:   http://localhost:${env.PORT}/auth`);
    });

    // ─── Graceful Shutdown ──────────────────────────────────────────────────
    const shutdown = async (signal: string) => {
      console.log(`\n⚠️  Received ${signal}. Shutting down gracefully...`);
      server.close(async () => {
        await prisma.$disconnect();
        console.log('✅ Database disconnected. Goodbye!');
        process.exit(0);
      });
    };

    process.on('SIGTERM', () => shutdown('SIGTERM'));
    process.on('SIGINT', () => shutdown('SIGINT'));
  } catch (err) {
    console.error('❌ Failed to start server:', err);
    await prisma.$disconnect();
    process.exit(1);
  }
}

bootstrap();
