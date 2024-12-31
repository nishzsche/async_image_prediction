import os
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4
from typing import Optional
from celery import Celery
from .db import SessionLocal
from .models import Prediction
from ..tasks.tasks import process_prediction

# Get the base directory of the project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))

# Define the uploads directory
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
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
    id: str
    status: str
    has_dog: Optional[bool]


@app.post("/image_prediction")
async def create_prediction(image: UploadFile):
    """Endpoint to create a new image prediction request."""
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not an image.")

    # Generate a unique ID for the prediction
    prediction_id = str(uuid4())

    # Save the uploaded image
    image_path = os.path.join(UPLOAD_DIR, f"{prediction_id}.jpg")
    with open(image_path, "wb") as buffer:
        buffer.write(await image.read())

    # Store metadata in the database
    db = SessionLocal()
    db_prediction = Prediction(
        id=prediction_id,
        status="PENDING",
        has_dog=None,
    )
    db.add(db_prediction)
    db.commit()
    db.close()

    # Dispatch the Celery task
    process_prediction.delay(prediction_id)

    return JSONResponse(
        status_code=200,
        content={
            "id": prediction_id,
            "status": "PENDING",
            "has_dog": None,
        },
    )


@app.get("/image_prediction/{prediction_id}")
async def get_prediction_status(prediction_id: str):
    """Endpoint to retrieve the status of a prediction."""
    db = SessionLocal()
    prediction = db.query(Prediction).filter(Prediction.id == prediction_id).first()
    db.close()

    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found.")

    return JSONResponse(
        status_code=200,
        content={
            "id": str(prediction.id),
            "status": prediction.status,
            "has_dog": prediction.has_dog,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
