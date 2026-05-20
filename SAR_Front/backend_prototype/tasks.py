import os
import time
from celery import Celery
from PIL import Image
from osgeo import gdal
import numpy as np

# Configure Celery
# In production, use environment variables
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
app = Celery('tiff_processor', broker=REDIS_URL, backend=REDIS_URL)

@app.task(bind=True, name='tasks.process_tiff', acks_late=True)
def process_tiff(self, file_path: str, output_dir: str, task_id: str, options: dict = None):
    """
    Asynchronous task to process large TIFF files.
    """
    if not options:
        options = {}
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    max_size = options.get('max_size', 512)
    quality = options.get('quality', 80)
    
    output_path = os.path.join(output_dir, f"{task_id}_thumb.webp")
    
    ds = None
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'message': 'Opening file...'})
        
        # 1. Open with GDAL
        ds = gdal.Open(file_path, gdal.GA_ReadOnly)
        if not ds:
            raise Exception("Failed to open TIFF file with GDAL")
            
        width = ds.RasterXSize
        height = ds.RasterYSize
        bands = ds.RasterCount
        
        self.update_state(state='PROCESSING', meta={'progress': 30, 'message': 'Reading raster data...'})
        
        # 2. Read as array (with downsampling if possible via ReadAsArray buf_size)
        # Calculate target size while maintaining aspect ratio
        ratio = min(max_size / width, max_size / height) if (width > max_size or height > max_size) else 1
        target_width = int(width * ratio)
        target_height = int(height * ratio)
        
        # Read data directly into target size (GDAL handles resampling efficiently)
        # Note: For very large files, this is memory efficient as GDAL does block reading + resampling
        # If overview exists, GDAL uses it automatically.
        data = ds.ReadAsArray(buf_xsize=target_width, buf_ysize=target_height)
        
        self.update_state(state='PROCESSING', meta={'progress': 60, 'message': 'Converting to image...'})
        
        # 3. Convert to Pillow Image
        img = None
        
        if bands >= 3:
            # Assume RGB(A)
            # data shape is (bands, height, width) usually
            if len(data.shape) == 3:
                # Transpose to (height, width, bands)
                data = data.transpose(1, 2, 0)
                
                # Check dtype. If uint16, scale to uint8
                if data.dtype == np.uint16:
                     data = (data / 256).astype(np.uint8)
                elif data.dtype == np.float32:
                     # Simple min-max normalization or just clip
                     data = (np.clip(data, 0, 1) * 255).astype(np.uint8)

                if bands == 3:
                    img = Image.fromarray(data, 'RGB')
                elif bands >= 4:
                    img = Image.fromarray(data[:, :, :4], 'RGBA')
        else:
            # Grayscale or Palette
            if len(data.shape) == 3:
                 # Single band but shape (1, h, w)
                 data = data[0]
            
            if data.dtype == np.uint16:
                 data = (data / 256).astype(np.uint8)
            
            img = Image.fromarray(data, 'L')
            
        if not img:
            # Fallback
             img = Image.new('RGB', (target_width, target_height), (200, 200, 200))

        # 4. Save as WebP
        self.update_state(state='PROCESSING', meta={'progress': 80, 'message': 'Saving thumbnail...'})
        img.save(output_path, 'WEBP', quality=quality)
        
        return {
            'task_id': task_id,
            'status': 'completed',
            'output_path': output_path,
            'original_size': [width, height],
            'thumbnail_size': [target_width, target_height]
        }
        
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e
    finally:
        ds = None

