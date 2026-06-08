type StoreDefinition = {
  keyPath: string;
  indexes?: ReadonlyArray<{ name: string; keyPath: string }>;
};

type DatabaseDefinition = {
  name: string;
  version: number;
  stores: Record<string, StoreDefinition>;
};

const databasePromises = new Map<string, Promise<IDBDatabase>>();

export function openIndexedDb(definition: DatabaseDefinition): Promise<IDBDatabase> {
  const cacheKey = `${definition.name}:${definition.version}`;
  const cached = databasePromises.get(cacheKey);
  if (cached) {
    return cached;
  }

  const promise = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(definition.name, definition.version);

    request.onupgradeneeded = () => {
      const db = request.result;
      for (const [storeName, storeDefinition] of Object.entries(definition.stores)) {
        let store: IDBObjectStore;
        if (!db.objectStoreNames.contains(storeName)) {
          store = db.createObjectStore(storeName, {
            keyPath: storeDefinition.keyPath,
          });
        } else {
          store = request.transaction!.objectStore(storeName);
        }

        for (const index of storeDefinition.indexes ?? []) {
          if (!store.indexNames.contains(index.name)) {
            store.createIndex(index.name, index.keyPath);
          }
        }
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  databasePromises.set(cacheKey, promise);
  return promise;
}

export async function withIndexedDbStore<T>(
  definition: DatabaseDefinition,
  storeName: string,
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T> | void,
): Promise<T | undefined> {
  const db = await openIndexedDb(definition);
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(storeName, mode);
    const store = transaction.objectStore(storeName);
    const request = fn(store);
    let result: T | undefined;

    if (request) {
      request.onsuccess = () => {
        result = request.result;
      };
      request.onerror = () => reject(request.error);
    }

    transaction.oncomplete = () => resolve(result);
    transaction.onerror = () => reject(transaction.error);
  });
}
