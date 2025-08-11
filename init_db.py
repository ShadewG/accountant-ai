"""Initialize database with tables"""
import sys
from pathlib import Path

# Add the parent directory to the path
sys.path.append(str(Path(__file__).parent))

from src.models import Base, engine
from src.config import settings

if __name__ == "__main__":
    print(f"Creating database tables...")
    print(f"Database URL: {settings.database_url}")
    
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully!")
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")
        sys.exit(1)