interface CacheItem<T> {
  value: T;
  expiry: number;
}

export class CacheService {
  private cache: Map<string, CacheItem<any>> = new Map();

  /**
   * Set a value in the cache with a TTL (in seconds).
   */
  set<T>(key: string, value: T, ttlSeconds: number): void {
    const expiry = Date.now() + ttlSeconds * 1000;
    this.cache.set(key, { value, expiry });
  }

  /**
   * Get a value from the cache. Returns null if expired or missing.
   */
  get<T>(key: string): T | null {
    const item = this.cache.get(key);
    if (!item) {
      return null;
    }

    if (Date.now() > item.expiry) {
      this.cache.delete(key);
      return null;
    }

    return item.value;
  }

  /**
   * Delete a value from the cache.
   */
  delete(key: string): void {
    this.cache.delete(key);
  }

  /**
   * Clear the entire cache.
   */
  clear(): void {
    this.cache.clear();
  }
}

export const appCache = new CacheService();
