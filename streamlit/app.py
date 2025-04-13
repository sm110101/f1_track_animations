import streamlit as st
from pathlib import Path
import sys

# Set page config FIRST
st.set_page_config(layout="wide")

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
    st.title("F1 Track Animations")
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
        return df['driver_code'].tolist()

    drivers = get_drivers(selected_race)
    if not drivers:
        st.error(f"No drivers found for {selected_race}")
        st.stop()

    selected_driver = st.sidebar.selectbox("Select a Driver:", drivers)

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

            idx = frame_idx % frame_count
            selected_idx = selected_valid[idx]
            fastest_idx = fastest_valid[idx]

            ax.plot([selected_tel['X'].iloc[selected_idx]], [selected_tel['Y'].iloc[selected_idx]],
                    'ko', markersize=10, label=f'{selected_driver}', zorder=10)
            ax.plot([fastest_tel['X'].iloc[fastest_idx]], [fastest_tel['Y'].iloc[fastest_idx]],
                    'o', color='gold', markersize=10, label=f'{fastest_driver} (Fastest)', zorder=10)

            ax.set_xlim(min(selected_tel['X'].min(), fastest_tel['X'].min()) - 100,
                        max(selected_tel['X'].max(), fastest_tel['X'].max()) + 100)
            ax.set_ylim(min(selected_tel['Y'].min(), fastest_tel['Y'].min()) - 100,
                        max(selected_tel['Y'].max(), fastest_tel['Y'].max()) + 100)

            ax.axis('equal')
            ax.axis('off')
            ax.set_title(f'{selected_driver} vs Fastest Lap ({fastest_driver}) – {selected_race}', pad=20)
            ax.legend(loc='upper right')
            plt.tight_layout()

            return fig



        # ---------- UI ----------
        col1, col2 = st.columns([1, 3])
        with col1:
            play_button = st.button("▶️ Play Animation")

        frame_idx = st.slider("🕹️ Select Frame", 0, frame_count - 1, 0)
        fig = create_frame_plot(frame_idx)
        plot_placeholder = st.empty()  # Create a single placeholder for the plot
        plot_placeholder.pyplot(fig)

        if play_button:
            # Animate on the same plot with faster updates
            for frame in range(0, frame_count, 2):
                frame_idx = frame  # Update the frame index
                fig = create_frame_plot(frame_idx)
                plot_placeholder.pyplot(fig)
                plt.close(fig)

    except Exception as e:
        st.error(f"An error occurred: {e}")
        st.stop()

    


if __name__ == "__main__":
    main()