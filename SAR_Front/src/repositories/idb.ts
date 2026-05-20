export type StoreRecord = Record<string, unknown>

export class IdbStore<T extends StoreRecord> {
  private dbName: string
  private storeName: string
  private version: number

  constructor(dbName: string, storeName: string, version = 1) {
    this.dbName = dbName
    this.storeName = storeName
    this.version = version
  }

  private openLatest(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(this.dbName)
      req.onerror = () => reject(req.error)
      req.onsuccess = () => resolve(req.result)
    })
  }

  private openWithVersion(version: number): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(this.dbName, version)
      req.onerror = () => reject(req.error)
      req.onsuccess = () => resolve(req.result)
      req.onupgradeneeded = () => {
        const db = req.result
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName, { keyPath: 'id' })
        }
      }
    })
  }

  private open(): Promise<IDBDatabase> {
    return this.openWithVersion(this.version)
      .catch(async (e: any) => {
        if (e?.name !== 'VersionError') throw e
        const db = await this.openLatest()
        this.version = db.version
        return db
      })
      .then(async (db) => {
        this.version = Math.max(this.version, db.version)
        if (db.objectStoreNames.contains(this.storeName)) return db
        const bumped = Math.max(this.version + 1, db.version + 1)
        db.close()
        const next = await this.openWithVersion(bumped)
        this.version = next.version
        return next
      })
  }

  async getAll(): Promise<T[]> {
    const db = await this.open()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, 'readonly')
      const store = tx.objectStore(this.storeName)
      const req = store.getAll()
      req.onsuccess = () => resolve(req.result as T[])
      req.onerror = () => reject(req.error)
    })
  }

  async get(id: string): Promise<T | undefined> {
    const db = await this.open()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, 'readonly')
      const store = tx.objectStore(this.storeName)
      const req = store.get(id)
      req.onsuccess = () => resolve(req.result as T | undefined)
      req.onerror = () => reject(req.error)
    })
  }

  async put(value: T): Promise<void> {
    const db = await this.open()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, 'readwrite')
      const store = tx.objectStore(this.storeName)
      const req = store.put(value)
      req.onsuccess = () => resolve()
      req.onerror = () => reject(req.error)
    })
  }

  async delete(id: string): Promise<void> {
    const db = await this.open()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, 'readwrite')
      const store = tx.objectStore(this.storeName)
      const req = store.delete(id)
      req.onsuccess = () => resolve()
      req.onerror = () => reject(req.error)
    })
  }
}
