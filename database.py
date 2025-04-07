# streamlit_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
import os
import sqlite3  # Import sqlite3
import re  # For sanitizing names if needed
import logging  # Optional: for app logging
import time  # For time handling

# --- Configuration ---
DATABASE_FILE = "plant_data.db"
APP_LOG_FILE = "streamlit_app.log"
# --- End Configuration ---

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=APP_LOG_FILE, filemode='a')
# --- End Logging Setup ---

# (Sanitize/Desanitize functions remain the same)
def sanitize_table_name(name):
    if not isinstance(name, str): name = str(name)
    s = re.sub(r'[^\w\s-]', '', name); s = re.sub(r'\s+', '_', s).strip('_')
    if not s: return "_unknown_plant_"
    if not re.match(r'^[a-zA-Z_]', s): s = '_' + s
    return s

def desanitize_table_name(name):
    return name.replace('_', ' ').strip()

# (Streamlit config, title, logo remain the same)
st.set_page_config(page_title="Eden Renewables India LLP - UAT", page_icon="EDEN-Logo.png", layout="wide")
st.title("Eden Renewables India LLP - UAT")
st.write("UAT dashboard displaying Generation data from the database for selected Plants and SPVs.")
try: 
    st.sidebar.image("EDEN-Logo.png", use_container_width=True)
except Exception as e: 
    st.sidebar.warning(f"Could not load logo: {e}")

# --- Display Current Date and Time ---
clock_placeholder = st.sidebar.empty()  # Placeholder for the clock

# Function to update the clock
def update_clock():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clock_placeholder.write(f"**Current Date and Time:** {current_time}")

# --- Theme handling remains the same)
theme_option = st.sidebar.selectbox("Select Theme", options=["Light", "Dark", "Blue", "Green"])
dark_theme_css = """ <style> html, body, .stApp { background-color: #2B2B2B !important; color: white !important; } .stButton>button { background-color: #4CAF50; color: white; border: none; } .stDataFrame { color: white; } div[data-baseweb="select"] > div { background-color: #333333; color: white; } div[data-baseweb="popover"] { background-color: #333333 !important; color: white !important; } </style> """
blue_theme_css = """ <style> html, body, .stApp { background-color: #E0F7FA !important; color: black !important;} .stButton>button { background-color: #2196F3; color: white; border: none;} </style> """
green_theme_css = """ <style> html, body, .stApp { background-color: #E8F5E9 !important; color: black !important;} .stButton>button { background-color: #4CAF50; color: white; border: none;} </style> """
light_theme_css = """ <style> html, body, .stApp { background-color: white !important; color: black !important;} .stButton>button { background-color: #f44336; color: white; border: none;} </style> """
if theme_option == "Dark": 
    st.markdown(dark_theme_css, unsafe_allow_html=True)
elif theme_option == "Blue": 
    st.markdown(blue_theme_css, unsafe_allow_html=True)
elif theme_option == "Green": 
    st.markdown(green_theme_css, unsafe_allow_html=True)
else: 
    st.markdown(light_theme_css, unsafe_allow_html=True)

# --- Get Available Plants (Table Names) from DB ---
@st.cache_data(show_spinner=False)
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

# --- Load Data from DB ---
@st.cache_data(ttl=3600, show_spinner="Loading plant data...")
def load_data_from_db(selected_plant_names: list):
    """Loads data, performs conversions, and includes targeted debug prints."""
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
plant_options = get_available_plants_from_db()
if not plant_options: 
    st.warning("No plant data found."); 
    st.stop()

st.sidebar.header("Filters")
selected_plants = st.sidebar.multiselect("Select Plant(s)", options=plant_options, key="plant_selection")

# --- Load Data and Check State Immediately ---
df = load_data_from_db(selected_plants)

# --- Debug Print Immediately After Receiving df ---
if df is not None and not df.empty:
    # Retrieve unique SPV options based on selected plants
    if 'SPV' in df.columns:
        spv_options = sorted(df['SPV'].unique())
        selected_spvs = st.sidebar.multiselect("Select SPV(s)", options=spv_options, key="spv_selection")

        # Filter DataFrame based on selected SPVs
        if selected_spvs:
            df = df[df['SPV'].isin(selected_spvs)]
    else:
        st.warning("SPV column not found in the data.")


# --- Year Filter Logic ---
if 'Months' in df.columns and pd.api.types.is_datetime64_any_dtype(df['Months']):
    valid_years = df['Months'].dt.year.dropna().unique()
    year_options = sorted([int(y) for y in valid_years])
    
    # Create a year range selector
    selected_years = st.sidebar.multiselect("Select Year(s)", options=year_options, key="year_selection")
    
    # Filter the DataFrame based on the selected years
    if selected_years:
        df = df[df["Months"].dt.year.isin(selected_years)]
else:
    st.sidebar.warning("Months column not date format or not present.")

# --- Quarter Filter Logic ---
if 'Months' in df.columns and pd.api.types.is_datetime64_any_dtype(df['Months']):
    # Extract quarter information
    df['Quarter'] = df['Months'].dt.to_period('Q').astype(str)  # Convert to string format like '2023Q1'
    quarter_options = sorted(df['Quarter'].unique())
    
    # Create a quarter selector
    selected_quarters = st.sidebar.multiselect("Select Quarter(s)", options=quarter_options, key="quarter_selection")
    
    # Filter the DataFrame based on the selected quarters
    if selected_quarters:
        df = df[df['Quarter'].isin(selected_quarters)]
else:
    st.sidebar.warning("Months column not date format or not present.")

# --- Display Logic ---
if not selected_plants: 
    st.info("Select one or more Plants from the sidebar.")
elif df is None: 
    st.error("A critical error occurred loading data.")
elif df.empty and selected_plants: 
    st.warning(f"No data found in DB for: {', '.join(selected_plants)}.")
elif 'SPV' not in df.columns and df is not None and not df.empty: 
    st.warning("SPV column missing. Cannot display SPV details.")

# Display detailed sections only if df has data AND SPV column exists
if not df.empty and 'SPV' in df.columns:
    selected_plant = selected_plants[0] if selected_plants else "Unknown Plant"
    display_spvs = selected_spvs if selected_spvs else sorted(df['SPV'].astype(str).unique())
    logging.info(f"Displaying sections for SPVs: {display_spvs}")

    for spv in display_spvs:
        spv_loop_df = df[df["SPV"].astype(str) == spv].copy()
        if spv_loop_df.empty: 
            logging.warning(f"Skipping SPV '{spv}' - empty after loop filter."); 
            continue

        st.subheader(f"Plant: {selected_plant}")  # Show selected Plant
        st.write(f"SPV: {spv}")  # Show selected SPV
        logging.info(f"--- Generating display for SPV: {spv} ---")

        # Gauges for AC and DC Capacities
        ac_capacity = 0
        dc_capacity = 0
        if "AC Capacity (MW)" in spv_loop_df.columns and not spv_loop_df["AC Capacity (MW)"].empty: 
            potential_ac_capacity = pd.to_numeric(spv_loop_df["AC Capacity (MW)"].iloc[0], errors='coerce'); 
            ac_capacity = 0 if pd.isna(potential_ac_capacity) else potential_ac_capacity
        if "Connected DC Capacity (MWp)" in spv_loop_df.columns and not spv_loop_df["Connected DC Capacity (MWp)"].empty: 
            potential_dc_capacity = pd.to_numeric(spv_loop_df["Connected DC Capacity (MWp)"].iloc[0], errors='coerce'); 
            dc_capacity = 0 if pd.isna(potential_dc_capacity) else potential_dc_capacity
        
        max_gauge_value = max(float(ac_capacity), float(dc_capacity), 1.0) * 1.1
        col1, col2 = st.columns(2)
        
        with col1: 
            ac_capacity_gauge = go.Figure( 
                go.Indicator( 
                    mode="gauge+number", 
                    value=float(ac_capacity), 
                    title={"text": "AC Capacity (MW)"}, 
                    gauge={"axis": {"range": [0, max_gauge_value], "tickwidth": 1}, "bar": {"color": "blue"}}, 
                    number={'suffix': " MW", "font":{"size":18}}, 
                    title_font={"size":16}, 
                    domain={"x": [0.1, 0.9], "y": [0.1, 0.9]}, 
                )
            ); 
            ac_capacity_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20)); 
            st.plotly_chart(ac_capacity_gauge, use_container_width=True, key=f"ac_gauge_{spv}")
        
        with col2: 
            dc_capacity_gauge = go.Figure( 
                go.Indicator( 
                    mode="gauge+number", 
                    value=float(dc_capacity), 
                    title={"text": "Connected DC Capacity (MWp)"}, 
                    gauge={"axis": {"range": [0, max_gauge_value], "tickwidth": 1}, "bar": {"color": "orange"}}, 
                    number={'suffix': " MWp", "font":{"size":18}}, 
                    title_font={"size":16}, 
                    domain={"x": [0.1, 0.9], "y": [0.1, 0.9]}, 
                )
            ); 
            dc_capacity_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20)); 
            st.plotly_chart(dc_capacity_gauge, use_container_width=True, key=f"dc_gauge_{spv}")

        # Data Table
        st.write(f"**Monthly Data Table for {spv}**"); 
        available_columns_for_table = spv_loop_df.columns.tolist()
        # Exclude SPV, AC, and DC columns from the display
        excluded_columns = ['SPV', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']
        available_columns_for_table = [col for col in available_columns_for_table if col not in excluded_columns]
        
        # Set default columns to display
        default_columns = available_columns_for_table[:4]  # Display first four columns by default
        selected_columns_for_table = st.multiselect(f"Select columns for {spv} table", options=available_columns_for_table, default=default_columns, key=f"col_select_{spv}")
        
        if selected_columns_for_table:
            display_df = spv_loop_df[selected_columns_for_table].copy()
            if 'Months' in display_df.columns: 
                display_df['Months'] = pd.to_datetime(display_df['Months'], format='%b-%y', errors='coerce')  # Ensure Months are in datetime format
                display_df.sort_values(by='Months', inplace=True)  # Sort by Months in ascending order
                display_df['Months'] = display_df['Months'].dt.strftime('%b-%y')  # Change format back to MMM-YY
                display_df.sort_values(by='Months', inplace=True)  # Sort again to ensure correct order

            # Format other columns
            for col in selected_columns_for_table:
                if col != 'Months':
                    if '%' in col:
                        # Convert decimal to percentage
                        display_df[col] = display_df[col].astype(float) * 100  # Convert to percentage
                        display_df[col] = display_df[col].map(lambda x: f"{x:.2f}%")  # Format as percentage
                    else:
                        display_df[col] = display_df[col].astype(float).map(lambda x: f"{x:.2f}")  # Format to 2 decimal places

            st.dataframe(display_df, use_container_width=True, hide_index=True, key=f"data_table_{spv}")

            # Summary Section
            summary_row = {}
            for col in selected_columns_for_table:
                if col != 'Months':
                    if '%' in col:
                        summary_row[col] = display_df[col].str.rstrip('%').astype(float).mean()  # Average for percentage columns
                        summary_row[col] = f"{summary_row[col]:.2f}%"  # Format as percentage
                    else:
                        summary_row[col] = display_df[col].str.replace(',', '').astype(float).sum()  # Sum for other columns
                        summary_row[col] = f"{summary_row[col]:.2f}"  # Format to 2 decimal places
            summary_row['Summary'] = 'Summary'  # Label for the summary row
            summary_df = pd.DataFrame([summary_row])
            
            # Display selected years in the summary
            if selected_years:
                st.write(f"**Summary for Year(s): {', '.join(map(str, selected_years))}**")
            else:
                st.write("**Summary**")
                
            st.dataframe(summary_df, use_container_width=True, hide_index=True)

        else: 
            st.write("_Select columns to display table._"); 
            logging.info(f"No columns selected for table {spv}.")
        st.divider()

# --- Footer ---
st.sidebar.info("Dashboard UAT - V3 (Database Backend)")
logging.info("--- Streamlit App Execution Cycle End ---")

# Update the clock
while True:
    update_clock()
    time.sleep(1)