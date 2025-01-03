import os
import pytest
import dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch
from async_image_prediction.api.app import app
from async_image_prediction.api.models import Base
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


# Fixture for mocking
@pytest.fixture(scope="module")
def mock_celery():
    with patch("async_image_prediction.api.app.celery_app.send_task") as mock_task:
        yield mock_task


# Test Celery Integration
def test_celery_task_queuing(mock_celery):
    with open("data/test/dogs.jpg", "rb") as image_file:
        client.post("/image_prediction", files={"image": image_file})

    # Ensure Celery's send_task was called
    assert mock_celery.called

    # Extract args
    args = mock_celery.call_args

    print(args, len(args), type(args), args[0], args[1])

    # Validate task name and arguments
    assert args[0][0] == "tasks.process_prediction"  # First argument is the task name
    assert len(args) == 2  # Task name and arguments
    assert isinstance(
        args[1]["args"], list
    )  # Second argument should be a list of task arguments
    assert len(args[1]["args"]) == 1  # Ensure there's one argument in the list
    assert args[1]["args"]  # Ensure the prediction_id was passed
