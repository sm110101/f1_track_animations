# f1_track_animations

A Streamlit web app for animating and comparing Formula 1 driver laps using telemetry data from the [FastF1](https://theoehrly.github.io/Fast-F1/) API. The app allows you to visualize a selected driver's lap against the overall fastest lap of the race, with interactive controls and variable overlays.

## Features

- **Race & Driver Selection:** Choose from several 2024 F1 races and all participating drivers.
- **Lap Comparison:** Compare a driver's fastest or slowest lap to the overall fastest lap of the race.
- **Telemetry Visualization:** Overlay variables like Speed, Throttle, Gear, Brake, or RPM on the track map.
- **Interactive Animation:** Play, pause, restart, or manually scrub through the lap animation.
- **Efficient Data Storage:** Uses DuckDB for fast, local querying of telemetry and summary data.

## How It Works

1. **Database Initialization:** On first run, the app downloads and processes telemetry data for selected races and stores it in a local DuckDB database (`database/track_db.duckdb`).
2. **User Interface:** The Streamlit app provides a sidebar for selecting race, driver, lap, and telemetry variable.
3. **Visualization:** The main panel displays an animated matplotlib plot of the selected lap, with color-coded telemetry and markers for both the selected and fastest drivers.

## [Try it out](https://dsan5200group25.streamlit.app/)