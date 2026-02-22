from backend.database.connection import get_db

# Re-export for convenient imports in route files
get_db_session = get_db
