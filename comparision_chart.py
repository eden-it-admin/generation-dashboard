# comparison_charts.py
import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import re
import logging
import os
from datetime import datetime

# --- Configuration ---
DATABASE_FILE = "plant_data.db"
APP_LOG_FILE = "comparison_charts.log"
# --- End Configuration ---

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=APP_LOG_FILE, filemode='a')
# --- End Logging Setup ---

# Function to sanitize table names
def sanitize_table_name(name):
    if not isinstance(name, str): name = str(name)
    s = re.sub(r'[^\w\s-]', '', name); s = re.sub(r'\s+', '_', s).strip('_')
    if not s: return "_unknown_plant_"
    if not re.match(r'^[a-zA-Z_]', s): s = '_' + s
    return s

# Function to desanitize table names
def desanitize_table_name(name):
    return name.replace('_', ' ').strip()

# Function to get available plants from the database
def get_available_plants_from_db():
    if not os.path.exists(DATABASE_FILE): 
        st.error(f"DB '{DATABASE_FILE}' not found."); 
        logging.error(f"DB '{DATABASE_FILE}' not found."); 
        return []
    try:
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor(); 
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"); 
            tables = cursor.fetchall()
            plant_names = sorted([desanitize_table_name(table[0]) for table in tables]); 
            logging.info(f"Found plants: {plant_names}"); 
            return plant_names
    except Exception as e: 
        st.error(f"DB Error: {e}"); 
        logging.error(f"DB Error: {e}", exc_info=True); 
        return []

# Function to load data from the database
def load_data_from_db(selected_plant_names: list):
    if not selected_plant_names: return pd.DataFrame()
    if not os.path.exists(DATABASE_FILE): 
        st.error(f"DB '{DATABASE_FILE}' not found."); 
        logging.error(f"DB '{DATABASE_FILE}' not found."); 
        return pd.DataFrame()

    df_list = []
    logging.info(f"Loading data for: {selected_plant_names}")
    all_dfs_read_successfully = True  # Flag to track if all selected plants were read ok

    try:
        with sqlite3.connect(DATABASE_FILE) as conn:
            for plant_name in selected_plant_names:
                table_name = plant_name  # Use the original table name
                logging.info(f"Querying: '{table_name}' for '{plant_name}'")
                try:
                    query = f'SELECT * FROM "{table_name}"'
                    df_plant = pd.read_sql_query(query, conn)
                    logging.info(f"Read {len(df_plant)} rows from '{table_name}'")

                    if df_plant.empty: 
                        logging.warning(f"No data in '{table_name}'."); 
                        continue  # Skip empty tables

                    # Convert 'Months' column to datetime format
                    if 'Months' in df_plant.columns:
                        df_plant['Months'] = pd.to_datetime(df_plant['Months'], errors='coerce')

                    df_list.append(df_plant)

                except Exception as e:  # Catch errors reading specific tables
                    st.error(f"Error reading table for plant '{plant_name}': {e}")
                    logging.error(f"Error reading table '{table_name}': {e}", exc_info=True)
                    all_dfs_read_successfully = False  # Mark that at least one table failed

        # --- Concatenation and Final Processing ---
        if df_list:
            logging.info("Concatenating loaded dataframes.")
            combined_df = pd.concat(df_list, ignore_index=True)

            # --- Apply Categorical Types ---
            if 'SPV' in combined_df.columns:
                combined_df['SPV'] = combined_df['SPV'].astype(str).astype('category')

            logging.info(f"Combined df shape: {combined_df.shape}")
            return combined_df
        elif all_dfs_read_successfully:
            logging.info("No dataframes in df_list after loop (all tables might be empty).")
            return pd.DataFrame()  # Return empty if all tables were empty
        else:
             logging.error("Errors occurred reading one or more plant tables. Returning None.")
             return None  # Indicate that loading wasn't fully successful
    except Exception as e:
        st.error(f"Fatal DB connection/read error: {e}")
        logging.error(f"Fatal DB error in load_data_from_db: {e}", exc_info=True)
        return None  # Indicate failure

# --- Main App Logic ---
st.set_page_config(page_title="Comparison Charts", layout="wide")

# Sidebar
st.sidebar.image("EDEN-Logo.png", use_container_width=True)  # Updated to use use_container_width
st.sidebar.markdown(f"**Current Date and Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Theme selection
theme_option = st.sidebar.selectbox("Select Theme", options=["Light", "Dark", "Blue", "Green"])
if theme_option == "Dark":
    st.markdown("""<style> html, body, .stApp { background-color: #2B2B2B !important; color: white !important; } </style>""", unsafe_allow_html=True)
elif theme_option == "Blue":
    st.markdown("""<style> html, body, .stApp { background-color: #E0F7FA !important; color: black !important;} </style>""", unsafe_allow_html=True)
elif theme_option == "Green":
    st.markdown("""<style> html, body, .stApp { background-color: #E8F5E9 !important; color: black !important;} </style>""", unsafe_allow_html=True)
else:
    st.markdown("""<style> html, body, .stApp { background-color: white !important; color: black !important;} </style>""", unsafe_allow_html=True)

# Get available plants
plant_options = get_available_plants_from_db()
if not plant_options: 
    st.warning("No plant data found."); 
    st.stop()

# Select plants
selected_plants = st.sidebar.multiselect("Select Plant(s)", options=plant_options, key="plant_selection")

# Load data
df = load_data_from_db(selected_plants)

# Check if data is loaded
if df is not None and not df.empty:
    # Create Year and Quarter columns for comparison
    df['Year'] = df['Months'].dt.year
    df['Quarter'] = df['Months'].dt.to_period('Q').astype(str)  # Convert to string format like '2023Q1'

    # Year Filter
    year_options = sorted(df['Year'].unique())
    selected_years = st.sidebar.multiselect("Select Year(s)", options=year_options, key="year_selection")

    # Filter DataFrame based on selected years
    if selected_years:
        df = df[df['Year'].isin(selected_years)]

    # SPV Selection
    spv_options = sorted(df['SPV'].unique())
    selected_spvs = st.sidebar.multiselect("Select SPV(s)", options=spv_options, key="spv_selection")

    # Filter DataFrame based on selected SPVs
    if selected_spvs:
        df = df[df['SPV'].isin(selected_spvs)]

    # Display area for Y-axis selection for each SPV
    st.header("Select Y-axis for Comparison")
    all_columns = df.columns.tolist()
    # Remove AC Capacity and Connected DC Capacity from the Y-axis options
    y_axis_options = [col for col in all_columns if col not in ['Months', 'Year', 'Quarter', 'SPV', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']]

    # Create a dictionary to hold Y-axis selections for each SPV
    y_axis_selections = {}
    for spv in selected_spvs:
        y_axis_selections[spv] = st.multiselect(f"Select Y-axis for {spv}", options=y_axis_options, default=[y_axis_options[0]], key=f"y_axis_selection_{spv}", max_selections=2)

    # Add radio button for chart type selection
    chart_type = st.radio("Select Chart Type", options=["Line Chart", "Bar Chart"], index=0)

    # Create separate charts for each selected SPV
    spv_charts = []
    for spv in selected_spvs:
        spv_data = df[df['SPV'] == spv]
        if not spv_data.empty:
            selected_y_axes = y_axis_selections[spv]
            if selected_y_axes:
                # Create a long format DataFrame for Plotly
                spv_long = spv_data.melt(id_vars=['Months'], value_vars=selected_y_axes, var_name='Metric', value_name='Value')

                # Format the 'Months' column to show "Jan-YY", "Feb-YY", etc.
                spv_long['Month_Year'] = spv_long['Months'].dt.strftime('%b-%y')

                # Create the chart based on the selected type
                if chart_type == "Line Chart":
                    comparison_chart = px.line(spv_long, x='Month_Year', y='Value', color='Metric', title=f"Comparison of {', '.join(selected_y_axes)} for SPV: {spv}", color_discrete_sequence=['orange', 'yellow'])
                else:  # Bar Chart
                    comparison_chart = px.bar(spv_long, x='Month_Year', y='Value', color='Metric', title=f"Comparison of {', '.join(selected_y_axes)} for SPV: {spv}", color_discrete_sequence=['orange', 'yellow'])

                spv_charts.append(comparison_chart)
            else:
                st.warning(f"No Y-axis metrics selected for SPV: {spv}")
        else:
            st.warning(f"No data available for SPV: {spv}")

    # Display charts side by side
    if spv_charts:
        cols = st.columns(len(spv_charts))
        for i, chart in enumerate(spv_charts):
            with cols[i]:
                st.plotly_chart(chart)

else:
    st.warning("No data available for the selected plants.")

# --- Footer ---
st.sidebar.info("Dashboard UAT - V3 (Database Backend)")
logging.info("--- Streamlit App Execution Cycle End ---")