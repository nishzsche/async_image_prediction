from celery import Celery
import torch
import os
import requests
import traceback
from ..api.db import SessionLocal
from ..api.models import Prediction
import logging
import dotenv

project_dir = os.path.join(os.path.dirname(__file__), os.pardir * 2)
dotenv_path = os.path.join(project_dir, ".env")
dotenv.load_dotenv(dotenv_path)

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="celery_worker.log",
    filemode="a",
)
logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    "tasks",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL"),
)

# Get the base directory of the project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Define the uploads directory
UPLOAD_DIR = os.path.join(BASE_DIR, "api", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

model_path = os.path.join(BASE_DIR, "models", "yolov5s.pt")


def download_yolo_model():
    """
    Download YOLOv5 model if it doesn't exist locally.
    """
    try:
        if not os.path.exists(model_path):
            logger.info("Downloading YOLOv5 model...")
            url = "https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5s.pt"
            response = requests.get(url, stream=True)
            with open(model_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            logger.info("YOLOv5 model downloaded successfully.")
        else:
            logger.info("YOLOv5 model already exists.")
    except Exception as e:
        logger.error(f"Failed to download YOLOv5 model: {e}")
        logger.error(traceback.format_exc())
        raise


@celery_app.task(name="tasks.process_prediction")
def process_prediction(prediction_id: str):
    """
    Background task to process an image prediction.

    Args:
        prediction_id (str): The unique ID for the prediction task.
    """
    logger.info(f"Starting prediction task for ID: {prediction_id}")

    try:
        # Path to the saved image
        image_path = os.path.join(UPLOAD_DIR, f"{prediction_id}.jpg")

        # Validate image file existence
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found at {image_path}")

        logger.info(f"Image file located at: {image_path}")

        # Download YOLO model if not available
        download_yolo_model()

        # Load YOLO model
        logger.info("Loading YOLOv5 model...")
        model = torch.hub.load("ultralytics/yolov5", "custom", path=model_path)
        logger.info("YOLOv5 model loaded successfully.")

        # Run inference
        logger.info("Running inference on the image...")
        results = model(image_path)
        logger.info("Inference completed.")

        # Process the results
        detections = results.xyxy[0].cpu().numpy()  # Extract detections
        logger.info(f"Detections: {detections}")

        # Check if any detection corresponds to a dog
        has_dog = any(
            model.names[int(detection[-1])].lower() == "dog" for detection in detections
        )
        logger.info(f"Prediction result for ID {prediction_id} - Has Dog: {has_dog}")

        # Update the database
        logger.info("Updating the database with prediction results...")
        db = SessionLocal()
        try:
            prediction = (
                db.query(Prediction).filter(Prediction.id == prediction_id).first()
            )
            if prediction:
                prediction.status = "DONE"
                prediction.has_dog = has_dog
                db.commit()
                logger.info(f"Database updated successfully for ID: {prediction_id}")
            else:
                logger.warning(
                    f"Prediction ID {prediction_id} not found in the database."
                )
        finally:
            db.close()

    except Exception as e:
        # Handle errors and update task status
        logger.error(f"Error processing prediction {prediction_id}: {e}")
        logger.error(traceback.format_exc())

        db = SessionLocal()
        try:
            prediction = (
                db.query(Prediction).filter(Prediction.id == prediction_id).first()
            )
            if prediction:
                prediction.status = "ERROR"
                prediction.has_dog = None
                db.commit()
                logger.info(
                    f"Database updated with ERROR status for ID: {prediction_id}"
                )
            else:
                logger.warning(
                    f"Prediction ID {prediction_id} not found in the database during error handling."
                )
        finally:
            db.close()
