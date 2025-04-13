import duckdb
import fastf1 as ff1
import pandas as pd
from pathlib import Path
import logging
logging.getLogger('fastf1').setLevel(logging.ERROR)
import warnings
warnings.filterwarnings("ignore")

# Constants
RACE_NAMES = [
    'Monaco Grand Prix',
    'Italian Grand Prix',
    'Singapore Grand Prix',
    'Belgian Grand Prix',
    'United States Grand Prix'
]
YEAR = 2024

def get_db_connection(read_only=False):
    db_path = Path(__file__).resolve().parent / 'track_db.duckdb'
    if not db_path.exists():
        print(f"[DEBUG] Database not found at path: {db_path}. Creating new database...")
        return duckdb.connect(str(db_path))
    else:
        print(f"[DEBUG] Connecting to DuckDB at path: {db_path}")
        return duckdb.connect(str(db_path), read_only=read_only)

def create_tables(con):
    """Creates lap_summary and telemetry tables"""
    con.execute("""
    CREATE TABLE IF NOT EXISTS lap_summary (
        year INTEGER,
        race_name VARCHAR,
        driver_code VARCHAR,
        lap_category VARCHAR,
        lap_number INTEGER,
        lap_time FLOAT            
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS telemetry (
        year INTEGER,
        race_name VARCHAR,
        driver_code VARCHAR,
        lap_category VARCHAR,
        lap_number INTEGER,
        telemetry_index INTEGER,
        X FLOAT,
        Y FLOAT,
        Speed FLOAT,
        Throttle FLOAT,
        nGear INTEGER,
        Brake FLOAT,
        RPM FLOAT,
        Distance FLOAT
    )
    """)

def insert_lap_summary(con, year, race_name, driver_code, lap_category, lap_number, lap_time):
    if isinstance(lap_time, pd.Timedelta):
        lap_time = lap_time.total_seconds()
    
    con.execute("""
    INSERT INTO lap_summary (year, race_name, driver_code, lap_category, lap_number, lap_time)
    VALUES (?, ?, ?, ?, ?, ?)
    """, [year, race_name, driver_code, lap_category, lap_number, lap_time])

def insert_telemetry(con, df_tel, year, race_name, driver_code, lap_category, lap_number):
    df_tel = df_tel.copy()
    df_tel['year'] = year
    df_tel['race_name'] = race_name
    df_tel['driver_code'] = driver_code
    df_tel['lap_category'] = lap_category
    df_tel['lap_number'] = lap_number
    df_tel['telemetry_index'] = df_tel.index

    columns = ['year', 'race_name', 'driver_code', 'lap_category', 
               'lap_number', 'telemetry_index', 'X', 'Y', 'Speed', 
               'Throttle', 'nGear', 'Brake', 'RPM', 'Distance']
    df_tel = df_tel[columns]

    con.register("temp_tel", df_tel)
    con.execute("INSERT INTO telemetry SELECT * FROM temp_tel")
    con.unregister("temp_tel")

def process_race_data(year, race_name, con):
    """Process a single race and store its data in the database"""
    print(f"Loading session for {race_name}...")
    session = ff1.get_session(year, race_name, 'Race')
    session.load()
    
    overall_fastest = None
    results = session.results
    driver_codes = results['Abbreviation'].tolist()

    for driver in driver_codes:
        driver_laps = session.laps.pick_driver(driver)
        driver_laps = driver_laps[driver_laps['Time'].notna()]
        
        if driver_laps.empty:
            print(f"No valid laps found for driver {driver}")
            continue

        try:
            # Process fastest lap
            fastest_lap = driver_laps.loc[driver_laps['LapTime'].idxmin()]
            lap_num_fast = fastest_lap['LapNumber']
            lap_time_fast = fastest_lap['LapTime']
            tel_fast = fastest_lap.get_telemetry().add_distance().reset_index(drop=True)
            
            insert_lap_summary(con, year, race_name, driver, 'fastest', lap_num_fast, lap_time_fast)
            insert_telemetry(con, tel_fast, year, race_name, driver, 'fastest', lap_num_fast)

            # Process slowest lap
            slowest_lap = driver_laps.loc[driver_laps['LapTime'].idxmax()]
            lap_num_slow = slowest_lap['LapNumber']
            lap_time_slow = slowest_lap['LapTime']
            tel_slow = slowest_lap.get_telemetry().add_distance().reset_index(drop=True)
            
            insert_lap_summary(con, year, race_name, driver, 'slowest', lap_num_slow, lap_time_slow)
            insert_telemetry(con, tel_slow, year, race_name, driver, 'slowest', lap_num_slow)

            if overall_fastest is None or lap_time_fast < overall_fastest[0]:
                overall_fastest = (lap_time_fast, driver, fastest_lap)

        except Exception as e:
            print(f"Error processing laps for driver {driver}: {str(e)}")
            continue

    # Process overall fastest lap
    if overall_fastest is not None:
        try:
            lap_time_overall, driver_overall, lap_overall = overall_fastest
            lap_num_overall = lap_overall['LapNumber']
            tel_overall = lap_overall.get_telemetry().add_distance().reset_index(drop=True)
            
            insert_lap_summary(con, year, race_name, driver_overall, 'overall', lap_num_overall, lap_time_overall)
            insert_telemetry(con, tel_overall, year, race_name, driver_overall, 'overall', lap_num_overall)
        except Exception as e:
            print(f"Error processing overall fastest lap: {str(e)}")

def initialize_database():
    """Initialize the database with all race data"""
    con = get_db_connection(read_only=False)
    create_tables(con)
    
    for race in RACE_NAMES:
        try:
            print(f"\nProcessing data for {race}...")
            process_race_data(YEAR, race, con)
            
            # Verify data was inserted
            count = con.execute("""
                SELECT COUNT(*) as count 
                FROM lap_summary 
                WHERE year = ? AND race_name = ?
            """, [YEAR, race]).fetchdf()['count'].iloc[0]
            print(f"Inserted {count} records for {race}")
            
        except Exception as e:
            print(f"Error processing data for {race}: {str(e)}")
            continue
    
    # Final verification
    total_count = con.execute("""
        SELECT COUNT(*) as count 
        FROM lap_summary 
        WHERE year = ?
    """, [YEAR]).fetchdf()['count'].iloc[0]
    print(f"\nTotal records in database: {total_count}")
    
    con.close()
    print("\nDatabase initialization complete!")

if __name__ == "__main__":
    initialize_database()