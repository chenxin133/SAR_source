import TiffWorker from '../workers/tiffThumbnail.worker.ts?worker';
import { IdbStore, type StoreRecord } from '../repositories/idb';

interface ThumbnailRecord extends StoreRecord {
  id: string; // hash of the file
  blob: Blob;
  timestamp: number;
}

const DB_NAME = 'SAR_TiffCache';
const STORE_NAME = 'thumbnails';
const VERSION = 1;

// We need to extend IdbStore or use it directly. 
// However, the existing IdbStore implementation in repositories/idb.ts 
// hardcodes 'keyPath: "id"' in onupgradeneeded.
// We must ensure the database is created correctly.
// Since IdbStore handles creation if store doesn't exist, we can reuse it.

class ThumbnailStore extends IdbStore<ThumbnailRecord> {
  constructor() {
    super(DB_NAME, STORE_NAME, VERSION);
  }
}

const store = new ThumbnailStore();

/**
 * Generates a unique ID for the file based on name, size, and last modified time.
 * For a more robust hash, we could read the first 1KB, but this is usually sufficient for client-side caching.
 */
function getFileId(file: File): string {
  // Simple hash for demo
  return `${file.name}-${file.size}-${file.lastModified}`;
}

export async function generateTiffThumbnail(file: File, maxSize: number = 256): Promise<string> {
  const id = getFileId(file);

  // 1. Check Cache
  try {
    const cached = await store.get(id);
    if (cached && cached.blob) {
      // Check if blob is valid
      if (cached.blob.size > 0) {
          console.log('TIFF Thumbnail hit cache:', id);
          return URL.createObjectURL(cached.blob);
      }
    }
  } catch (e) {
    console.warn('Failed to read from IDB:', e);
  }

  // 2. Process in Worker
  return new Promise((resolve, reject) => {
    const worker = new TiffWorker();

    worker.onmessage = (e) => {
      const { success, imageBitmap, error } = e.data;
      
      if (success && imageBitmap) {
        try {
          const canvas = document.createElement('canvas');
          canvas.width = imageBitmap.width;
          canvas.height = imageBitmap.height;
          
          const ctx = canvas.getContext('bitmaprenderer');
          if (ctx) {
             ctx.transferFromImageBitmap(imageBitmap);
          } else {
             const ctx2d = canvas.getContext('2d');
             ctx2d?.drawImage(imageBitmap, 0, 0);
          }
          
          canvas.toBlob(async (blob) => {
            if (blob) {
              // 3. Cache Result
              try {
                await store.put({
                  id,
                  blob,
                  timestamp: Date.now()
                });
              } catch (err) {
                console.warn('Failed to cache thumbnail:', err);
              }
              
              resolve(URL.createObjectURL(blob));
            } else {
              reject(new Error('Failed to convert canvas to blob'));
            }
            worker.terminate();
          }, 'image/png');
          
        } catch (err) {
          reject(err);
          worker.terminate();
        }
      } else {
        reject(new Error(error || 'Worker failed'));
        worker.terminate();
      }
    };

    worker.onerror = (err) => {
      reject(err);
      worker.terminate();
    };

    worker.postMessage({ file, maxSize });
  });
}

export async function clearThumbnailCache() {
    try {
        const all = await store.getAll();
        const now = Date.now();
        const MAX_AGE = 7 * 24 * 60 * 60 * 1000; // 7 days
        
        for (const item of all) {
            if (now - item.timestamp > MAX_AGE) {
                await store.delete(item.id);
            }
        }
    } catch (e) {
        console.error('Failed to clear cache', e);
    }
}

