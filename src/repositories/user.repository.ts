import { Prisma, User } from '@prisma/client';
import { prisma } from '../config/prisma';

/**
 * Repository layer for User table — all direct DB access lives here.
 * Services must not use `prisma` directly; they call these functions instead.
 */

/**
 * Find a user record by their unique email address.
 * @param email - The email address to look up (case-insensitive due to schema).
 * @returns The matching User or null if not found.
 */
export async function findUserByEmail(email: string): Promise<User | null> {
  return prisma.user.findUnique({ where: { email } });
}

/**
 * Find a user record by their unique primary key.
 * @param id - The user's CUID.
 * @returns The matching User or null if not found.
 */
export async function findUserById(id: string): Promise<User | null> {
  return prisma.user.findUnique({ where: { id } });
}

/**
 * Persist a new User record to the database.
 * @param data - The fields required to create the user.
 * @returns The newly created User.
 */
export async function createUser(data: Prisma.UserCreateInput): Promise<User> {
  return prisma.user.create({ data });
}

/**
 * Update fields of an existing user.
 * @param id - The user's CUID.
 * @param data - The fields to update.
 * @returns The updated User.
 */
export async function updateUser(
  id: string,
  data: Prisma.UserUpdateInput,
): Promise<User> {
  return prisma.user.update({ where: { id }, data });
}
