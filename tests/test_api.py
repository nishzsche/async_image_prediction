import os
import pytest
import dotenv
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from async_image_prediction.api.app import app
from async_image_prediction.api.models import Prediction, Base
from async_image_prediction.api.db import get_db

project_dir = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
dotenv_path = os.path.join(project_dir, ".env")
dotenv.load_dotenv(dotenv_path)

# Test database setup
engine = create_engine(os.getenv("TEST_DATABASE_URL"))
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)


# Override the get_db dependency to use the test database
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# Create tables before running tests
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    print("Creating test database tables...")
    Base.metadata.create_all(bind=engine)
    yield
    print("Dropping test database tables...")
    Base.metadata.drop_all(bind=engine)


# Test API Endpoints
def test_post_image_prediction():
    with open("data/test/dogs.jpg", "rb") as image_file:
        response = client.post("/image_prediction", files={"image": image_file})

    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    assert response.json()["has_dog"] is None


def test_get_image_prediction_pending():
    # Insert a pending prediction into the database
    db = TestingSessionLocal()
    test_uuid = "22fe0d33-6d01-4563-a9cf-37c560978665"
    prediction = Prediction(id=test_uuid, status="PENDING", has_dog=None)
    db.add(prediction)
    db.commit()
    db.close()

    # Make the API call
    response = client.get(f"/image_prediction/{test_uuid}")

    # Assert the response
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    assert response.json()["has_dog"] is None


def test_get_image_prediction_done():
    # Insert a done prediction into the database
    db = TestingSessionLocal()
    test_uuid = "33fe0d33-6d01-4563-a9cf-37c560978666"
    prediction = Prediction(id=test_uuid, status="DONE", has_dog=True)
    db.add(prediction)
    db.commit()
    db.close()

    # Make the API call
    response = client.get(f"/image_prediction/{test_uuid}")

    # Assert the response
    assert response.status_code == 200
    assert response.json()["status"] == "DONE"
    assert response.json()["has_dog"] is True


def test_invalid_image_file():
    response = client.post(
        "/image_prediction",
        files={"image": ("..data/test/not_an_image.txt", b"invalid content")},
    )

    assert response.status_code == 400
    assert "Invalid file type" in response.text


def test_invalid_prediction_id():
    invalid_uuid = str(
        uuid.uuid4()
    )  # Generate a valid UUID that doesn't exist in the database
    response = client.get(f"/image_prediction/{invalid_uuid}")
    assert response.status_code == 404
    assert "Prediction not found" in response.text


# Test Error Handling
def test_internal_prediction_error():
    # Insert an error prediction into the database
    db = TestingSessionLocal()
    test_uuid = "44fe0d33-6d01-4563-a9cf-37c560978667"
    prediction = Prediction(id=test_uuid, status="ERROR", has_dog=None)
    db.add(prediction)
    db.commit()
    db.close()

    # Make the API call
    response = client.get(f"/image_prediction/{test_uuid}")

    # Assert the response
    assert response.status_code == 200
    assert response.json()["status"] == "ERROR"
    assert response.json()["has_dog"] is None
