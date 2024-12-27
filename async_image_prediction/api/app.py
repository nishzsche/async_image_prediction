from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4
from typing import Optional
from celery import Celery
from ultralytics import YOLO
import os

# Path to store uploaded images
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Create the FastAPI app
app = FastAPI()

# Initialize Celery
celery_app = Celery(
    "tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0"
)

# In-memory database to store prediction statuses
predictions = {}


class PredictionStatus(BaseModel):
    image_prediction_id: str
    status: str
    has_dog: Optional[bool]


@app.post("/image_prediction")
async def create_prediction(image: UploadFile):
    """Endpoint to create a new image prediction request."""
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not an image.")

    prediction_id = str(uuid4())
    predictions[prediction_id] = {"status": "PENDING", "has_dog": None}

    # Dispatch the task to Celery
    celery_app.send_task("tasks.process_prediction", args=[prediction_id])

    return JSONResponse(
        status_code=200,
        content={
            "image_prediction_id": prediction_id,
            "status": "PENDING",
            "has_dog": None,
        },
    )


@app.get("/image_prediction/{prediction_id}")
async def get_prediction_status(prediction_id: str):
    """Endpoint to retrieve the status of a prediction."""
    prediction = predictions.get(prediction_id)

    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found.")

    return JSONResponse(
        status_code=200, content={"image_prediction_id": prediction_id, **prediction}
    )


@celery_app.task(name="tasks.process_prediction")
def process_prediction(prediction_id: str):
    """Background task to handle the prediction."""
    try:
        # Path to the saved image
        image_path = os.path.join(UPLOAD_DIR, f"{prediction_id}.jpg")

        # Load YOLO model
        model = YOLO("yolov5s.pt")  # Load a pre-trained YOLOv5s model

        # Run inference
        results = model(image_path)
        detections = results[0].boxes.data.numpy()  # Get detected boxes and classes

        # Check if any detection corresponds to a dog
        has_dog = False
        for detection in detections:
            class_id = int(detection[-1])  # Class ID is usually the last value
            if model.names[class_id].lower() == "dog":
                has_dog = True
                break

        # Update the prediction result
        predictions[prediction_id]["status"] = "DONE"
        predictions[prediction_id]["has_dog"] = has_dog
    except Exception as e:
        predictions[prediction_id]["status"] = "ERROR"
        predictions[prediction_id]["has_dog"] = None
        print(f"Error in processing prediction {prediction_id}: {e}")


# To be moved: Save this code in 'async_image_prediction/api/app.py'
# Run the application with a simple test server (use Uvicorn in production)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
