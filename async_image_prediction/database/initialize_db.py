from async_image_prediction.api.models import init_db

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Database initialized with the updated schema.")
