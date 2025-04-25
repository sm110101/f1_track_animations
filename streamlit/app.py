import streamlit as st
from pathlib import Path
import sys

st.set_page_config(
    layout="wide",
    page_title="F1 Track Animations",
    initial_sidebar_state="expanded"
)

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from database.init_db import initialize_database, get_db_connection

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.colors import ListedColormap
from matplotlib.collections import LineCollection
import numpy as np
import fastf1 as ff1
import fastf1.plotting
import time


driver_dict = {
    'RUS': {'name': 'George Russell', 'team': 'Mercedes'},
    'ALB': {'name': 'Alexander Albon', 'team': 'Williams'},
    'HUL': {'name': 'Nico Hülkenberg', 'team': 'Haas'},
    'SAI': {'name': 'Carlos Sainz Jr.', 'team': 'Ferrari'},
    'HAM': {'name': 'Lewis Hamilton', 'team': 'Mercedes'},
    'BOT': {'name': 'Valtteri Bottas', 'team': 'Kick Sauber'},
    'MAG': {'name': 'Kevin Magnussen', 'team': 'Haas'},
    'LAW': {'name': 'Liam Lawson', 'team': 'Visa Cash App RB'},
    'COL': {'name': 'Franco Colapinto', 'team': 'Williams'},
    'ALO': {'name': 'Fernando Alonso', 'team': 'Aston Martin'},
    'PIA': {'name': 'Oscar Piastri', 'team': 'McLaren'},
    'RIC': {'name': 'Daniel Ricciardo', 'team': 'Visa Cash App RB'},
    'VER': {'name': 'Max Verstappen', 'team': 'Red Bull Racing'},
    'STR': {'name': 'Lance Stroll', 'team': 'Aston Martin'},
    'PER': {'name': 'Sergio Pérez', 'team': 'Red Bull Racing'},
    'OCO': {'name': 'Esteban Ocon', 'team': 'Alpine'},
    'GAS': {'name': 'Pierre Gasly', 'team': 'Alpine'},
    'ZHO': {'name': 'Zhou Guanyu', 'team': 'Kick Sauber'},
    'TSU': {'name': 'Yuki Tsunoda', 'team': 'Visa Cash App RB'},
    'LEC': {'name': 'Charles Leclerc', 'team': 'Ferrari'},
    'NOR': {'name': 'Lando Norris', 'team': 'McLaren'},
    'SAR': {'name': 'Logan Sargeant', 'team': 'Williams'}
}


def ensure_database_exists():
    """Check if database exists, if not create and populate it"""
    db_path = Path("database/track_db.duckdb")
    if not db_path.exists():
        st.info("Initializing database...")
        initialize_database()
        st.success("Database initialized!")
    else:
        st.info("Database already exists!")

def main():
    st.title("F1 Track Animations (2024)")
    st.markdown("""
    **Overview:**            
    - Animation of Formula 1 telemetry data comparing a selected driver's lap against the fastest lap of the race. 
    - Data is sourced from the FastF1 API and stored in a DuckDB database for efficient querying.
    **How to use:**
    1. Select a race and driver from the sidebar
    2. Choose between their fastest or slowest lap
    3. Pick a telemetry variable to visualize on the track (Speed, Throttle, Gear, etc.)
    4. Use the play/pause button to control the animation
    5. Drag the slider to manually scrub through the lap
    """)
    ensure_database_exists()

    # Constants
    RACE_NAMES = ['Monaco Grand Prix', 'Italian Grand Prix', 'Singapore Grand Prix', 
                  'Belgian Grand Prix', 'United States Grand Prix']

    # -- Sidebar: Race selection
    selected_race = st.sidebar.selectbox("Select a Race:", RACE_NAMES)

    # -- Driver selection
    @st.cache_data
    def get_drivers(race_name):
        con = get_db_connection()
        df = con.execute("""
            SELECT DISTINCT driver_code 
            FROM lap_summary 
            WHERE year = ? AND TRIM(race_name) = ?
        """, [2024, race_name]).fetchdf()
        con.close()
        # Create a mapping of driver names to codes for the dropdown
        driver_options = {f"{driver_dict[code]['name']} ({code})": code for code in df['driver_code'].tolist()}
        return driver_options

    driver_options = get_drivers(selected_race)
    if not driver_options:
        st.error(f"No drivers found for {selected_race}")
        st.stop()

    selected_driver_name = st.sidebar.selectbox("Select a Driver:", list(driver_options.keys()))
    selected_driver = driver_options[selected_driver_name]  # This is the driver code

    # -- Lap selection
    @st.cache_data
    def get_lap_options(race_name, driver_code):
        con = get_db_connection()
        df = con.execute("""
            SELECT lap_number, lap_category, lap_time 
            FROM lap_summary
            WHERE year = ? AND TRIM(race_name) = ? AND driver_code = ?
        """, [2024, race_name, driver_code]).fetchdf()
        con.close()
        return df

    lap_df = get_lap_options(selected_race, selected_driver)
    if lap_df.empty:
        st.error(f"No laps found for {selected_driver} in {selected_race}")
        st.stop()

    try:
        fastest_lap = lap_df[lap_df['lap_category'] == 'fastest'].iloc[0]
        slowest_lap = lap_df[lap_df['lap_category'] == 'slowest'].iloc[0]
        lap_options = {
            f"Lap {fastest_lap['lap_number']} (Fastest)": fastest_lap['lap_number'],
            f"Lap {slowest_lap['lap_number']} (Slowest)": slowest_lap['lap_number']
        }
        selected_lap_label = st.sidebar.selectbox("Select Lap:", list(lap_options.keys()))
        selected_lap_number = lap_options[selected_lap_label]
    except IndexError:
        st.error(f"Could not find fastest/slowest laps for {selected_driver}")
        st.stop()

    # -- Telemetry variable selection
    telemetry_var = st.sidebar.selectbox("Telemetry Variable:", ['Speed', 'Throttle', 'nGear', 'Brake', 'RPM'])

    # -- Get telemetry and fastest lap data
    try:
        con = get_db_connection()

        selected_tel = con.execute("""
            SELECT * FROM telemetry
            WHERE year = ? AND TRIM(race_name) = ? AND driver_code = ? AND lap_number = ?
        """, [2024, selected_race, selected_driver, int(selected_lap_number)]).fetchdf()

        fastest_driver_df = con.execute("""
            SELECT driver_code, lap_number FROM lap_summary
            WHERE year = ? AND TRIM(race_name) = ? AND lap_category = 'overall'
        """, [2024, selected_race]).fetchdf()

        if fastest_driver_df.empty:
            st.error(f"No overall fastest lap found for {selected_race}")
            st.stop()

        fastest_driver = fastest_driver_df['driver_code'].iloc[0]
        fastest_lap_number = int(fastest_driver_df['lap_number'].iloc[0])

        fastest_tel = con.execute("""
            SELECT * FROM telemetry
            WHERE year = ? AND TRIM(race_name) = ? AND driver_code = ? AND lap_number = ?
        """, [2024, selected_race, fastest_driver, fastest_lap_number]).fetchdf()

        con.close()

    
        # Precompute valid indices for animation
        selected_valid = selected_tel[['X', 'Y']].dropna().index.to_numpy()
        fastest_valid = fastest_tel[['X', 'Y']].dropna().index.to_numpy()

        frame_count = min(len(selected_valid), len(fastest_valid))
        frame_indices = np.linspace(0, frame_count - 1, frame_count).astype(int)

        # Add interpolation points between frames
        interpolation_factor = 3  # Number of interpolated points between each frame
        interpolated_indices = np.linspace(0, frame_count - 1, frame_count * interpolation_factor)

        # Prepare color and segment data
        x = selected_tel['X'].to_numpy()
        y = selected_tel['Y'].to_numpy()
        color = selected_tel[telemetry_var].to_numpy()

        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)

        cmap_dict = {
            'Speed': 'plasma',
            'Throttle': 'viridis',
            'nGear': ListedColormap(plt.get_cmap('jet')(np.linspace(0.1, 0.9, 8))),
            'Brake': ListedColormap(['gray', 'red']),
            'RPM': 'inferno'
        }

        units = {
            'Speed': 'km/h',
            'Throttle': '%',
            'nGear': 'Gear',
            'Brake': 'On/Off',
            'RPM': 'RPM'
        }

        # ---------- PLOT FUNCTION ----------
        def create_frame_plot(frame_idx):
            fig, ax = plt.subplots(figsize=(12, 7))

            norm = plt.Normalize(np.nanmin(color), np.nanmax(color))
            lc = LineCollection(segments, cmap=cmap_dict[telemetry_var], norm=norm)
            lc.set_array(color)
            lc.set_linewidth(4)
            ax.add_collection(lc)

            ax.plot(x, y, color='lightgray', linewidth=1, alpha=0.5)

            cbar = plt.colorbar(lc, ax=ax)
            cbar.set_label(f'{telemetry_var} ({units[telemetry_var]})')

            # Calculate interpolated positions
            idx = frame_idx / interpolation_factor
            prev_idx = int(idx)
            next_idx = min(prev_idx + 1, frame_count - 1)
            alpha = idx - prev_idx  # interpolation factor between 0 and 1

            # Interpolate selected driver position
            selected_prev = selected_valid[prev_idx]
            selected_next = selected_valid[next_idx]
            selected_x = (1 - alpha) * selected_tel['X'].iloc[selected_prev] + alpha * selected_tel['X'].iloc[selected_next]
            selected_y = (1 - alpha) * selected_tel['Y'].iloc[selected_prev] + alpha * selected_tel['Y'].iloc[selected_next]

            # Interpolate fastest driver position
            fastest_prev = fastest_valid[prev_idx]
            fastest_next = fastest_valid[next_idx]
            fastest_x = (1 - alpha) * fastest_tel['X'].iloc[fastest_prev] + alpha * fastest_tel['X'].iloc[fastest_next]
            fastest_y = (1 - alpha) * fastest_tel['Y'].iloc[fastest_prev] + alpha * fastest_tel['Y'].iloc[fastest_next]

            ax.plot([selected_x], [selected_y],
                    'ko', color='black', markersize=10, 
                    label=f"{driver_dict[selected_driver]['name']}", zorder=10)
            ax.plot([fastest_x], [fastest_y],
                    'o', color='gold', markersize=10, 
                    label=f"{driver_dict[fastest_driver]['name']} (Fastest)", zorder=10)

            ax.set_xlim(min(selected_tel['X'].min(), fastest_tel['X'].min()) - 100,
                        max(selected_tel['X'].max(), fastest_tel['X'].max()) + 100)
            ax.set_ylim(min(selected_tel['Y'].min(), fastest_tel['Y'].min()) - 100,
                        max(selected_tel['Y'].max(), fastest_tel['Y'].max()) + 100)

            ax.axis('equal')
            ax.axis('off')
            ax.set_title(f'{driver_dict[selected_driver]["name"]} vs Fastest Lap ({driver_dict[fastest_driver]["name"]})')
            plt.suptitle(f'{selected_race} 2024', fontsize=18, fontweight='bold', x=0.40)

            # Adjust legend position based on race
            if selected_race in ['Singapore Grand Prix', 'United States Grand Prix']:
                ax.legend(loc='upper right', bbox_to_anchor=(1.05, 1.05))
            else:
                ax.legend(loc='upper right')

            plt.tight_layout()

            return fig

        # ---------- UI ----------
        col1, col2 = st.columns([1, 3])
        with col1:
            # Initialize session state variables
            if 'is_playing' not in st.session_state:
                st.session_state.is_playing = False
            if 'current_frame' not in st.session_state:
                st.session_state.current_frame = 0
            
            # Play/Pause button
            if st.button("▶️ Play Animation" if not st.session_state.is_playing else "⏸️ Pause Animation"):
                st.session_state.is_playing = not st.session_state.is_playing
            
            # Restart button
            if st.button("🔄 Restart Animation"):
                st.session_state.current_frame = 0
                st.session_state.is_playing = False

        # Frame slider
        frame_idx = st.slider("🕹️ Select Frame", 0, frame_count * interpolation_factor - 1, 
                            st.session_state.current_frame)
        st.session_state.current_frame = frame_idx
        
        fig = create_frame_plot(frame_idx)
        plot_placeholder = st.empty()
        plot_placeholder.pyplot(fig)

        if st.session_state.is_playing:
            # Animate with interpolated frames, skipping every other frame
            for frame in range(st.session_state.current_frame, frame_count * interpolation_factor, 10):
                if not st.session_state.is_playing:  # Check if paused
                    break
                st.session_state.current_frame = frame
                fig = create_frame_plot(frame)
                plot_placeholder.pyplot(fig)
                plt.close(fig)
                time.sleep(0.0000000000001)  # Minimal sleep time

    except Exception as e:
        st.error(f"An error occurred: {e}")
        st.stop()

    


if __name__ == "__main__":
    main()