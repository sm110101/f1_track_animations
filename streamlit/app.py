import streamlit as st
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
from database.init_db import initialize_database, get_db_connection

def ensure_database_exists():
    db_path = Path("database/track_db.duckdb")
    if not db_path.exists():
        st.info("Initializing database...")
        initialize_database()
        st.success("Database initialized!")
    else:
        st.info("Database already exists!")

def main():
    ensure_database_exists()
    
    

if __name__ == "__main__":
    main()