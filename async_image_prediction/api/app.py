import os
from fastapi import FastAPI, UploadFile, Depends
from fastapi.responses import PlainTextResponse
from fastapi.exception_handlers import HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from uuid import uuid4
from typing import Optional
import mimetypes
from celery import Celery
import dotenv
from .db import get_db
from .models import Prediction

project_dir = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
dotenv_path = os.path.join(project_dir, ".env")
dotenv.load_dotenv(dotenv_path)

# Get the base directory of the project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))

# Define the uploads directory
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Create the FastAPI app
app = FastAPI()

# Initialize Celery
celery_app = Celery(
    "tasks", broker=os.getenv("REDIS_URL"), backend=os.getenv("REDIS_URL")
)

# In-memory database to store prediction statuses
predictions = {}


class PredictionStatus(BaseModel):
    id: str
    status: str
    has_dog: Optional[bool]


def get_celery():
    return celery_app


@app.post("/image_prediction")
async def create_prediction(
    image: UploadFile, celery=Depends(get_celery), db=Depends(get_db)
):
    """Endpoint to create a new image prediction request."""
    if not image.content_type.startswith("image/") or not mimetypes.guess_extension(
        image.content_type
    ):
        raise HTTPException(status_code=400, detail="Invalid file type.")

    # Generate a unique ID for the prediction
    prediction_id = str(uuid4())

    # Save the uploaded image
    image_path = os.path.join(UPLOAD_DIR, f"{prediction_id}.jpg")
    with open(image_path, "wb") as buffer:
        buffer.write(await image.read())

    # Store metadata in the database
    db_prediction = Prediction(
        id=prediction_id,
        status="PENDING",
        has_dog=None,
    )
    db.add(db_prediction)
    db.commit()

    # Dispatch the Celery task
    celery.send_task("tasks.process_prediction", args=[prediction_id])

    return PredictionStatus(id=prediction_id, status="PENDING", has_dog=None)


@app.get("/image_prediction/{prediction_id}")
async def get_prediction_status(prediction_id: str, db: Session = Depends(get_db)):
    """Endpoint to retrieve the status of a prediction."""
    prediction = db.query(Prediction).filter(Prediction.id == prediction_id).first()
    db.close()

    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found.")

    return PredictionStatus(
        id=str(prediction.id), status=prediction.status, has_dog=prediction.has_dog
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@app.get("/health")
async def health_check():
    try:
        # Check Redis
        celery_app.control.ping(timeout=1)

        # Check Database
        with get_db() as db:
            db.execute("SELECT 1")
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "details": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
