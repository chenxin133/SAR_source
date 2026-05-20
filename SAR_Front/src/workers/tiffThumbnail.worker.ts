import { fromBlob, type GeoTIFF, type GeoTIFFImage } from 'geotiff';

interface WorkerMessage {
  file: Blob;
  maxSize?: number;
}

interface WorkerResponse {
  success: boolean;
  imageBitmap?: ImageBitmap;
  error?: string;
}

self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  const { file, maxSize = 256 } = e.data;

  try {
    const tiff: GeoTIFF = await fromBlob(file);
    const image: GeoTIFFImage = await tiff.getImage(); // Get first image
    
    const width = image.getWidth();
    const height = image.getHeight();

    // Calculate downsample ratio
    let targetWidth = width;
    let targetHeight = height;
    
    if (width > maxSize || height > maxSize) {
      const ratio = Math.min(maxSize / width, maxSize / height);
      targetWidth = Math.round(width * ratio);
      targetHeight = Math.round(height * ratio);
    }

    // Read rasters with resizing
    // Note: geotiff.js readRasters with width/height performs nearest-neighbor resampling
    const rasters = await image.readRasters({
      width: targetWidth,
      height: targetHeight,
      // interleave: true // We'll handle planar data manually for flexibility
    });

    // Handle different band counts
    let r: any, g: any, b: any, a: any;
    
    // Check if rasters is a TypedArray (interleaved) or Array of TypedArrays (planar)
    // readRasters returns (TypedArray | Array<TypedArray>) & { width, height }
    // Since we didn't specify interleave: true, it should be an array of bands.
    const bands = rasters as any as (TypedArray[]); 
    
    if (bands.length >= 3) {
      r = bands[0];
      g = bands[1];
      b = bands[2];
      a = bands.length > 3 ? bands[3] : null;
    } else {
      // Grayscale
      r = g = b = bands[0];
      a = bands.length > 1 ? bands[1] : null;
    }

    // Create RGBA buffer
    const bufferSize = targetWidth * targetHeight * 4;
    const data = new Uint8ClampedArray(bufferSize);
    
    // Normalize function
    const bitDepth = image.getBitsPerSample ? image.getBitsPerSample()[0] : 8;
    // Simple scaling for 16-bit to 8-bit
    const scale = bitDepth > 8 ? 255 / (Math.pow(2, bitDepth) - 1) : 1;

    for (let i = 0; i < targetWidth * targetHeight; i++) {
        const valR = r[i] * scale;
        const valG = g[i] * scale;
        const valB = b[i] * scale;
        const valA = a ? a[i] * scale : 255;

        data[i * 4] = valR;
        data[i * 4 + 1] = valG;
        data[i * 4 + 2] = valB;
        data[i * 4 + 3] = valA;
    }

    // Use ImageData constructor (available in workers in modern browsers)
    const imageData = new ImageData(data, targetWidth, targetHeight);
    
    // Convert to ImageBitmap for transfer
    // @ts-ignore
    const bitmap = await createImageBitmap(imageData);

    // @ts-ignore
    self.postMessage({ success: true, imageBitmap: bitmap } as WorkerResponse, [bitmap]);

  } catch (err: any) {
    console.error('TIFF Worker Error:', err);
    // @ts-ignore
    self.postMessage({ success: false, error: err.message } as WorkerResponse);
  }
};

// Helper type for TypedArray
type TypedArray = Int8Array | Uint8Array | Uint8ClampedArray | Int16Array | Uint16Array | Int32Array | Uint32Array | Float32Array | Float64Array;

