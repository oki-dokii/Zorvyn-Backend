# Finance Dashboard API

## Project Overview
The Finance Dashboard API is a resilient, modern Node.js backend tailored for high-performance financial data management. Built on Express and styled in TypeScript, it integrates Prisma ORM for type-safe database queries. Features include robust Zod schema validation, Role-Based Access Control (RBAC), automatic audit logging, intelligent aggregations cached gracefully to prevent database bloat, and highly-detailed globally centralized error handling routines mapped closely to HTTP status codes.

## Setup Instructions
1. **Clone the repository.**
2. **Install dependencies:** `npm install`
3. **Set up PostgreSQL database:** Create a database named `finance_dashboard`.
4. **Environment configuration:** Copy `.env.example` to `.env` and fill the variables.
5. **Push database schema:** `npx prisma db push`
6. **Generate Prisma Client:** `npx prisma generate`
7. **Start development server:** `npm run dev`

## Environment Variables
| Variable | Description |
|-----------|-------------|
| `PORT` | API Server port (default 3000) |
| `NODE_ENV` | deployment space (`development`, `production`, `test`) |
| `DATABASE_URL` | Postgres connection string |
| `JWT_SECRET` | Secret key for access token |
| `JWT_REFRESH_SECRET` | Secret key for refresh token |
| `CORS_ORIGINS` | Comma-separated allowed URLs |

## Role Permissions Matrix
| Feature | VIEWER | ANALYST | ADMIN |
|---------|--------|---------|-------|
| Login/Register/Me | ✅ | ✅ | ✅ |
| View own transactions| ✅ | ✅ | ✅ |
| View all transactions| ❌ | ❌ | ✅ |
| Create transactions | ❌ | ✅ | ✅ |
| Update transactions | ❌ | ✅ | ✅ |
| Delete transactions | ❌ | ❌ | ✅ |
| View Dashboard Summary | ✅ | ✅ | ✅ |
| View Dashboard Monthly | ❌ | ✅ | ✅ |

## API Endpoints

### Auth Routings
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | None | Register a new user |
| POST | `/auth/login` | None | Get tokens |
| POST | `/auth/refresh` | None | Rotate refresh token |
| POST | `/auth/logout` | None | Invalidated token |
| GET | `/auth/me` | JWT | Get active user profile |

### Transaction Routings
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/transactions` | JWT | Search and filter transactions |
| POST | `/api/transactions` | JWT (An, Ad) | Create transaction |
| GET | `/api/transactions/:id` | JWT | Find single transaction |
| PATCH | `/api/transactions/:id` | JWT (An, Ad) | Update transaction |
| DELETE | `/api/transactions/:id` | JWT (Ad) | Soft delete transaction |

### Dashboard Routings
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/dashboard/summary` | JWT | Basic metrics and sums |
| GET | `/api/dashboard/recent-activity`| JWT | Log of last N transactions with running balance |
| GET | `/api/dashboard/category-breakdown`| JWT (An, Ad)| Breakdown categories with percentages |
| GET | `/api/dashboard/monthly-trend` | JWT (An, Ad)| Extract monthly array containing income+expense |
| GET | `/api/dashboard/top-categories` | JWT (An, Ad)| High expenses sorting |

## Design Decisions
1. **Repository Pattern**: Extracted DB access entirely from services to explicitly guarantee logic independence, drastically increasing testability and keeping the door open for swappable DB schemas in the future without crippling business models.
2. **Prisma over Raw SQL**: Prisma is leveraged extensively over raw implementations to secure complete build-time Type Safety and strict DB migrations preventing critical schema drifts.
3. **Soft Deletes**: Transactions are gracefully hidden (`deletedAt`) rather than obliterated to explicitly configure a clean, immutable analytical audit trail.
4. **Zod at the Route Layer**: Deployed schemas strictly at route entry-points so we immediately "fail fast" with bad requests, preventing corrupt data structures from ever creeping into robust business services.
5. **Composable RBAC Middleware**: Handled role authorizations functionally (`requireRole('ADMIN', 'ANALYST')`) directly mapping into Express router middleware blocks making endpoint scopes instantly readable and effortlessly extensible.

## Assumptions
- **Data Safety Protocol**: Analyst cannot delete to prevent accidental data loss. Deletion routes are strictly enforced behind `ADMIN` roles.
- **Read-Only Scaling**: Viewers are explicitly read-only to protect data integrity.
- **Financial Exactitude**: Amounts are strictly stored as `Decimal` types instead of `Float` to absolutely avoid rounding and floating-point computational errors natively during financial sums.

## Example Curl Commands

**Register User**
```bash
curl -X POST http://localhost:3000/auth/register \
-H "Content-Type: application/json" \
-d '{"email":"test@test.com", "password":"Password1!", "role":"ADMIN"}'
```

**Login**
```bash
curl -X POST http://localhost:3000/auth/login \
-H "Content-Type: application/json" \
-d '{"email":"test@test.com", "password":"Password1!"}'
```

**Create Transaction**
```bash
curl -X POST http://localhost:3000/api/transactions \
-H "Authorization: Bearer <TOKEN>" \
-H "Content-Type: application/json" \
-d '{"amount": 540, "type": "INCOME", "category": "Salary", "date": "2024-10-10T00:00:00Z"}'
```

**Get Dashboard Summary**
```bash
curl -X GET http://localhost:3000/api/dashboard/summary \
-H "Authorization: Bearer <TOKEN>"
```
