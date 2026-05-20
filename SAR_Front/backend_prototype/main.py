import os
import shutil
import uuid
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from tasks import process_tiff, app as celery_app

app = FastAPI(title="TIFF Processing Service")

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "thumbnails"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str

@app.post("/api/v1/tiff/upload", response_model=TaskResponse, status_code=202)
async def upload_tiff(
    file: UploadFile = File(...),
    max_size: int = 512,
    quality: int = 80
):
    if not file.filename.lower().endswith(('.tif', '.tiff')):
        raise HTTPException(status_code=400, detail="Only TIFF files are supported")
    
    # Generate unique ID
    task_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}.tif")
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Trigger Celery task
    task = process_tiff.delay(
        file_path=os.path.abspath(file_path),
        output_dir=os.path.abspath(OUTPUT_DIR),
        task_id=task_id,
        options={'max_size': max_size, 'quality': quality}
    )
    
    return {
        "task_id": task.id,
        "status": "pending",
        "message": "File uploaded, compression task started."
    }

@app.get("/api/v1/tiff/tasks/{task_id}")
async def get_task_status(task_id: str):
    task_result = celery_app.AsyncResult(task_id)
    
    response = {
        "task_id": task_id,
        "status": task_result.status.lower(),
        "result": None,
        "error": None
    }
    
    if task_result.state == 'PENDING':
        response["progress"] = 0
    elif task_result.state == 'PROCESSING':
        response["progress"] = task_result.info.get('progress', 0)
        response["message"] = task_result.info.get('message', '')
    elif task_result.state == 'SUCCESS':
        response["progress"] = 100
        response["result"] = task_result.result
        # Add URL construction here in real app
        response["result"]["url"] = f"/static/thumbnails/{task_id}_thumb.webp"
    elif task_result.state == 'FAILURE':
        response["error"] = str(task_result.result)
        
    return response

# Serve static files for demo purposes
from fastapi.staticfiles import StaticFiles
app.mount("/static/thumbnails", StaticFiles(directory=OUTPUT_DIR), name="thumbnails")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
