# --- test_app.py (Modified) ---

import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import os
import datetime # <-- Import datetime
from PIL import Image # <-- Import Pillow Image


# Connect to the SQLite database
DATABASE_FILE = 'plant_database.db'  # Update with your new database file path
EXCEL_FILE_PATH = os.path.join("data", "data.xlsx") # Path to the Excel file
LOGO_PATH = os.path.join("assets", "EDEN-Logo.png") # <-- DEFINE LOGO PATH (change 'logo.png' if needed)

# Set the page configuration to wide mode
st.set_page_config(layout="wide", page_title="Eden Renewables - Generation Dashboard") # Added page title


@st.cache_data # Cache database data loading
def load_data(plant_names=None, spvs=None, years=None, quarters=None):
    # Connect to the database
    conn = sqlite3.connect(DATABASE_FILE)

    # Create a query to fetch data based on filters
    query = "SELECT name FROM sqlite_master WHERE type='table';"
    tables_df = pd.read_sql(query, conn)
    available_tables = tables_df['name'].tolist()

    # If no plant_names filter is applied initially, just return table names
    if plant_names is None:
        conn.close()
        # Ensure names like 'SECI-III' are returned correctly if they exist
        return available_tables

    # Filter plant_names to only include tables that actually exist
    valid_plant_names = [name for name in plant_names if name in available_tables]
    if not valid_plant_names:
        conn.close()
        return pd.DataFrame() # Return empty DataFrame if no valid plants selected

    # Load data from the specified plant tables
    df_list = []
    for plant_name in valid_plant_names:
        try:
            # Use quotes around table name to handle special characters like '-'
            df = pd.read_sql(f"SELECT * FROM '{plant_name}'", conn)
            df['Plant'] = plant_name  # Add a column for Plant name
            df_list.append(df)
        except pd.io.sql.DatabaseError as e:
            st.warning(f"Could not read table '{plant_name}': {e}")
            continue # Skip this table if error

    # Check if any data was loaded
    if not df_list:
        conn.close()
        return pd.DataFrame() # Return empty DataFrame if no data could be loaded

    # Concatenate all dataframes
    all_data = pd.concat(df_list, ignore_index=True)
    conn.close() # Close connection after reading

    # Ensure 'Months' column exists and convert to datetime safely
    if 'Months' in all_data.columns:
        all_data['Months'] = pd.to_datetime(all_data['Months'], errors='coerce')
        all_data = all_data.dropna(subset=['Months']) # Remove rows where conversion failed
    else:
         # If no 'Months' column, cannot filter by year/quarter
         if years or quarters:
             st.warning("Cannot filter by Year/Quarter: 'Months' column not found in data.")
         # Apply SPV filter if possible, even without Months
         if spvs and 'SPV' in all_data.columns:
             all_data = all_data[all_data['SPV'].isin(spvs)]
         elif spvs:
             st.warning("Cannot filter by SPV: 'SPV' column not found in data.")
         return all_data

    # Apply filters (only if 'Months' column existed)
    if spvs:
        # Check if 'SPV' column exists before filtering
        if 'SPV' in all_data.columns:
            all_data = all_data[all_data['SPV'].isin(spvs)]
        else:
            st.warning("Cannot filter by SPV: 'SPV' column not found in data.")

    if years:
        all_data = all_data[all_data['Months'].dt.year.isin(years)]

    if quarters:
        # Allow 'All' to bypass quarter filtering
        actual_quarters = [q for q in quarters if q != 'All']
        if actual_quarters: # Only filter if specific quarters (not 'All') are selected
             # Ensure quarter values are integers
             valid_quarters = [q for q in actual_quarters if isinstance(q, int)]
             if valid_quarters:
                 all_data = all_data[all_data['Months'].dt.quarter.isin(valid_quarters)]

    return all_data

@st.cache_data # Cache Excel data loading
def load_excel_data(file_path, sheet_name):
    """Load data from the specified sheet in the Excel file."""
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            st.error(f"Error loading Excel: File not found at {file_path}")
            return None
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        # Basic validation: Check for expected columns (adjust as needed)
        if sheet_name == "Plant_Data" and not all(col in df.columns for col in ['Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']):
             st.warning(f"Sheet 'Plant_Data' in {file_path} might be missing expected columns ('Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)'). Check spelling and case.")
        elif sheet_name == "SPV_Data" and not all(col in df.columns for col in ['SPV', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']):
             st.warning(f"Sheet 'SPV_Data' in {file_path} might be missing expected columns ('SPV', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)'). Check spelling and case.")
        return df
    except Exception as e:
        st.error(f"Error loading Excel file '{file_path}', sheet '{sheet_name}': {e}")
        return None

# Streamlit UI
st.title("Eden Renewables - Project Generation Dashboard - UAT")
st.markdown("This dashboard provides insights into the generation data of various plants.")

# --- Data Loading ---
# Load plant names (table names) from DB
available_plant_names = load_data() # Will now include 'SECI-III' if table exists

# Load Excel data for AC and DC capacities
plant_capacity_data = load_excel_data(EXCEL_FILE_PATH, "Plant_Data")
spv_capacity_data = load_excel_data(EXCEL_FILE_PATH, "SPV_Data")

# --- Sidebar ---
# ADD LOGO AT THE TOP OF THE SIDEBAR
if os.path.exists(LOGO_PATH):
    try:
        logo_image = Image.open(LOGO_PATH)
        st.sidebar.image(logo_image, width=150) # Adjust width as needed
    except Exception as e:
        st.sidebar.error(f"Error loading logo: {e}")
else:
    st.sidebar.warning(f"Logo file not found at: {LOGO_PATH}")

st.sidebar.header("Filter Options")


selected_plants = st.sidebar.multiselect("Select Plant", options=available_plant_names) # Options based on DB tables


# --- Dependent Filters ---
spv_options = []
year_options = []
filtered_db_data = pd.DataFrame() # Initialize as empty DF

if selected_plants:
    # Load data *only* to get filter options (SPV, Year)
    # Pass None for other filters to avoid premature filtering
    options_data = load_data(plant_names=selected_plants, spvs=None, years=None, quarters=None)

    if not options_data.empty:
        if 'SPV' in options_data.columns:
            # Ensure SPV names with special chars are handled correctly
            spv_options = sorted(options_data['SPV'].astype(str).unique())
        else:
            st.sidebar.warning("SPV column not found in database data.")

        if 'Months' in options_data.columns:
            # Ensure 'Months' is datetime before extracting year
            months_dt = pd.to_datetime(options_data['Months'], errors='coerce')
            year_options = sorted(months_dt.dt.year.dropna().unique().astype(int), reverse=True)
        else:
            st.sidebar.warning("Months column not found in database data.")

selected_spvs = st.sidebar.multiselect("Select SPV", options=spv_options)
selected_years = st.sidebar.multiselect("Select Year", options=year_options)
quarter_options = ['All', 1, 2, 3, 4]
# Set default for Quarter to 'All' for clarity
selected_quarters = st.sidebar.multiselect("Select Quarter", options=quarter_options, default=['All'])


# --- Main Area Logic ---
if selected_plants:
    # Load actual data based on ALL filters now
    filtered_db_data = load_data(selected_plants, selected_spvs, selected_years, selected_quarters)

    # Check if filtered_data is empty or if required capacity data is missing
    if filtered_db_data.empty and selected_plants and (selected_spvs or selected_years or selected_quarters != ['All']):
         st.warning("No data found in the database for the selected filters.")
    elif plant_capacity_data is None:
         st.error("Plant capacity data from Excel could not be loaded. Gauges cannot be displayed.")
    elif spv_capacity_data is None:
         st.error("SPV capacity data from Excel could not be loaded. Gauges cannot be displayed.")
    # Proceed even if filtered_db_data is empty, to show plant gauges
    elif plant_capacity_data is not None and spv_capacity_data is not None:

        # Create a section for each selected plant
        for plant_name in selected_plants: # plant_name will be 'SECI-III' if selected
            st.subheader(f"Plant: {plant_name}")

            # --- PLANT GAUGE Calculation (Uses Excel Data) ---
            plant_ac_capacity = 0
            plant_dc_capacity = 0

            # Lookup uses the potentially updated plant_name ('SECI-III')
            plant_info = plant_capacity_data[plant_capacity_data['Plant'] == plant_name]
            if not plant_info.empty:
                # Use .iloc[0] to get the value from the first matching row
                # Add .get() with default to handle potential missing columns gracefully
                plant_ac_capacity = plant_info['AC Capacity (MW)'].iloc[0]
                plant_dc_capacity = plant_info['Connected DC Capacity (MWp)'].iloc[0]
            else:
                st.warning(f"Capacity data not found for Plant '{plant_name}' in Plant_Data sheet.")

            # Ensure capacities are numeric, default to 0 if not
            plant_ac_capacity = pd.to_numeric(plant_ac_capacity, errors='coerce') or 0
            plant_dc_capacity = pd.to_numeric(plant_dc_capacity, errors='coerce') or 0

            # Create gauge charts for Plant capacities from Excel
            col1, col2 = st.columns(2)

            with col1:
                # Determine gauge range, ensuring max is at least a small value if capacity is 0
                gauge_max_ac = max(1, plant_ac_capacity * 1.2)
                fig_ac_plant = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=plant_ac_capacity,
                    title={'text': f"{plant_name} AC Capacity (MW)"},
                    gauge={'axis': {'range': [0, gauge_max_ac]},
                           'bar': {'color': "darkorange"},
                           'steps': [{'range': [0, gauge_max_ac], 'color': "lightgray"}]}
                ))
                fig_ac_plant.update_layout(width=400, height=300, margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(fig_ac_plant, use_container_width=True, key=f"gauge_ac_plant_{plant_name}")

            with col2:
                 # Determine gauge range
                gauge_max_dc = max(1, plant_dc_capacity * 1.2)
                fig_dc_plant = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=plant_dc_capacity,
                    title={'text': f"{plant_name} DC Capacity (MWp)"},
                    gauge={'axis': {'range': [0, gauge_max_dc]},
                           'bar': {'color': "chocolate"},
                           'steps': [{'range': [0, gauge_max_dc], 'color': "lightgray"}]}
                ))
                fig_dc_plant.update_layout(width=400, height=300, margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(fig_dc_plant, use_container_width=True, key=f"gauge_dc_plant_{plant_name}")

            # --- SPV Section ---
            # Filter DATABASE data for the current plant
            plant_db_data_filtered = filtered_db_data[filtered_db_data['Plant'] == plant_name]

            # Get unique SPVs for THIS plant FROM THE FILTERED DB DATA
            if 'SPV' in plant_db_data_filtered.columns:
                 # Get SPVs present in the data *after* filtering by year/quarter etc.
                 spvs_in_filtered_data = plant_db_data_filtered['SPV'].unique()

                 # Display gauges and data for each relevant SPV
                 for spv_name in spvs_in_filtered_data:
                    st.markdown(f"--- \n **SPV: {spv_name}**") # Add separator

                    # --- SPV GAUGE Calculation (Uses Excel Data) ---
                    spv_ac_capacity = 0
                    spv_dc_capacity = 0

                    # Lookup uses the spv_name from the filtered data
                    spv_info = spv_capacity_data[spv_capacity_data['SPV'] == spv_name]
                    if not spv_info.empty:
                        # Add .get() with default
                        spv_ac_capacity = spv_info['AC Capacity (MW)'].iloc[0]
                        spv_dc_capacity = spv_info['Connected DC Capacity (MWp)'].iloc[0]
                    else:
                         st.warning(f"Capacity data not found for SPV '{spv_name}' in SPV_Data sheet.")

                    # Ensure capacities are numeric, default to 0 if not
                    spv_ac_capacity = pd.to_numeric(spv_ac_capacity, errors='coerce') or 0
                    spv_dc_capacity = pd.to_numeric(spv_dc_capacity, errors='coerce') or 0

                    # Create columns for side-by-side display of SPV gauges
                    col_spv1, col_spv2 = st.columns(2)

                    # Create gauge for SPV AC Capacity from Excel
                    with col_spv1:
                        gauge_max_spv_ac = max(1, spv_ac_capacity * 1.2)
                        fig_ac_spv = go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=spv_ac_capacity,
                            title={'text': f"AC Capacity (MW)"},
                            gauge={'axis': {'range': [0, gauge_max_spv_ac]},
                                   'bar': {'color': "GoldenRod"},
                                   'steps': [{'range': [0, gauge_max_spv_ac], 'color': "lightgray"}]}
                        ))
                        fig_ac_spv.update_layout(width=400, height=300, margin=dict(l=20, r=20, t=50, b=20))
                        st.plotly_chart(fig_ac_spv, use_container_width=True, key=f"gauge_ac_spv_{plant_name}_{spv_name}")

                    # Create gauge for SPV Connected DC Capacity from Excel
                    with col_spv2:
                        gauge_max_spv_dc = max(1, spv_dc_capacity * 1.2)
                        fig_dc_spv = go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=spv_dc_capacity,
                            title={'text': f"DC Capacity (MWp)"},
                            gauge={'axis': {'range': [0, gauge_max_spv_dc]},
                                   'bar': {'color': "Gold"},
                                   'steps': [{'range': [0, gauge_max_spv_dc], 'color': "lightgray"}]}
                        ))
                        fig_dc_spv.update_layout(width=400, height=300, margin=dict(l=20, r=20, t=50, b=20))
                        st.plotly_chart(fig_dc_spv, use_container_width=True, key=f"gauge_dc_spv_{plant_name}_{spv_name}")

                    # --- SPV Database Data Table ---
                    # Filter the DATABASE data specifically for this SPV within this Plant (already done)
                    spv_db_data_filtered = plant_db_data_filtered[plant_db_data_filtered['SPV'] == spv_name]

                    if not spv_db_data_filtered.empty:

                        # Formatting the DataFrame (using original function)
                        def format_dataframe(df_to_format):
                            df = df_to_format.copy() # Work on a copy
                            # Format 'Months' column to Date (MMM-YY)
                            if 'Months' in df.columns:
                                # Ensure it's datetime before formatting
                                df['Months'] = pd.to_datetime(df['Months'], errors='coerce').dt.strftime('%b-%y')

                            # Select only numeric columns for formatting (excluding known non-numeric like 'Months', 'SPV', 'Plant')
                            numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns

                            for col in numeric_cols:
                                # Skip capacity columns if they exist in DB data (they shouldn't be formatted this way)
                                if col in ['AC Capacity (MW)', 'Connected DC Capacity (MWp)']:
                                     df[col] = df[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")
                                     continue

                                # Check if column name indicates percentage
                                is_percent_col = '%' in col or col == 'Soil Loss (%)' # Added explicit check

                                try:
                                    # Convert to numeric, coercing errors. Crucial before math/formatting.
                                    numeric_series = pd.to_numeric(df[col], errors='coerce')

                                    if is_percent_col:
                                        # Format as percentage with 2 decimal places
                                        df[col] = numeric_series.apply(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "N/A")
                                    else:
                                        # Format as number with 2 decimal places
                                        df[col] = numeric_series.apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")
                                except Exception as e:
                                     st.warning(f"Could not format column '{col}': {e}")
                                     df[col] = df[col].astype(str) # Keep as string if formatting fails

                            return df

                        # Apply formatting to the specific SPV's database data
                        formatted_data = format_dataframe(spv_db_data_filtered)

                        # Replace remaining NaN/NaT (e.g., in non-numeric cols) with "N/A" or similar for display
                        formatted_data = formatted_data.fillna("N/A")

                        # Column selection filter for the current SPV's database data
                        db_cols_to_exclude = ['SPV', 'Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']
                        available_columns = [col for col in spv_db_data_filtered.columns if col not in db_cols_to_exclude]

                        # Ensure 'Months' is first if available
                        if 'Months' in available_columns:
                             available_columns.remove('Months')
                             available_columns.insert(0, 'Months')

                        # Set default columns (e.g., 'Months' + next 5, or fewer if not available)
                        default_cols_count = min(len(available_columns), 6)
                        default_columns = available_columns[:default_cols_count]

                        selected_columns = st.multiselect(
                            f"Select database columns to display for {spv_name}:",
                            options=available_columns,
                            default=default_columns,
                            key=f"columns_{plant_name}_{spv_name}"
                        )

                        # Display the formatted DATABASE data in the corresponding section
                        if selected_columns:
                            # Display only selected columns, reset index
                            st.dataframe(formatted_data[selected_columns].reset_index(drop=True), use_container_width=True, hide_index=True)

                            # --- Summary Section (Based on Selected DB Columns) ---
                            st.markdown("**Summary of Displayed Database Columns**")

                            summary_data = {}
                            # Use the original unformatted data for calculations
                            original_spv_db_data = spv_db_data_filtered[selected_columns]

                            # Define the columns that should be summed
                            columns_to_sum = ["Budget Gen (MWHr)", "Actual Gen (MWHr)"] # EXACT NAMES REQUIRED

                            for col in selected_columns:
                                if col == 'Months': # Skip 'Months' for summary calculation
                                    continue

                                # Attempt to convert column to numeric for calculation
                                numeric_col = pd.to_numeric(original_spv_db_data[col], errors='coerce')

                                # Check if column is effectively numeric after coercion (ignoring NaNs)
                                if pd.api.types.is_numeric_dtype(numeric_col.dropna()):

                                    # Check if the column name indicates it should be summed
                                    if col in columns_to_sum:
                                        sum_value = numeric_col.sum()
                                        # Format as number with 2 decimal places
                                        summary_data[col] = f"{sum_value:.2f}" if pd.notna(sum_value) else "N/A"

                                    # Check for percentage columns (explicit or by name convention)
                                    elif '%' in col or col == 'Soil Loss (%)':
                                        avg_value = numeric_col.mean()
                                        # Format as percentage with 2 decimal places
                                        summary_data[col] = f"{avg_value * 100:.2f}%" if pd.notna(avg_value) else "N/A"

                                    # --- All OTHER numeric columns: Calculate AVERAGE ---
                                    else:
                                        avg_value = numeric_col.mean()
                                        # Format as number with 2 decimal places
                                        summary_data[col] = f"{avg_value:.2f}" if pd.notna(avg_value) else "N/A"

                                else:
                                    summary_data[col] = "Non-numeric" # Indicate non-numeric columns

                            # Create a single-row DataFrame for summary
                            if summary_data: # Only display if there's something to summarize
                                summary_df = pd.DataFrame([summary_data])
                                st.dataframe(
                                    summary_df.reset_index(drop=True),
                                    use_container_width=True,
                                    hide_index=True # Keep index hidden
                                )
                            else:
                                st.caption("No numeric columns selected for summary.")

                        else:
                            st.caption("No columns selected for display.") # Message if no columns selected
                    else:
                        # This message appears if DB data exists for the plant, but not for this specific SPV after filters
                        st.caption(f"No database data found for SPV '{spv_name}' matching the current Plant/Year/Quarter filters.")

            elif not plant_db_data_filtered.empty:
                 # This case handles if the plant's data exists but has no 'SPV' column
                 st.warning(f"'SPV' column not found in the database data for Plant '{plant_name}'. Cannot display SPV details.")
            # No else needed here - if plant_db_data_filtered is empty, the main warning about filters appears earlier


# Add a message if no plants are selected at all
elif not available_plant_names:
    st.error(f"No plant data tables found in the database: {DATABASE_FILE}") # Show DB file name
else:
    st.info("Select one or more plants from the sidebar to view data.")


# --- FOOTER ---
st.markdown("---") # Add a horizontal rule before the footer

# Get current time
now = datetime.datetime.now()
# Format for display (e.g., 27-Oct-2023 15:45:30)
current_time_str = now.strftime("%d-%b-%Y %H:%M:%S")

# Use columns for layout if desired, or simple markdown
# col_footer_1, col_footer_2 = st.columns([3, 1]) # Adjust ratios as needed

# with col_footer_1:
     # Replace with your desired footer text
#    st.markdown(f"<span style='font-size: 12px;'>© {now.year} Eden Renewables India LLP. All rights reserved.</span>", unsafe_allow_html=True)

# with col_footer_2:
    # Display current date and time, right-aligned potentially
#    st.markdown(f"<span style='font-size: 12px; float: right;'>Last Refresh: {current_time_str}</span>", unsafe_allow_html=True)


# --- ALTERNATIVE FOOTER (Simpler, centered) ---
footer_html = f"""
<style>
    .footer {{
        position: relative; /* Changed from fixed to avoid overlap */
        bottom: 0;
        width: 100%;
        background-color: #f1f1f1;
        color: #333;
        text-align: center;
        padding: 10px 0;
        font-size: 12px;
        border-top: 1px solid #e0e0e0;
        margin-top: 20px; /* Add space above footer */
    }}
</style>
<div class="footer">
    © {now.year} Eden Renewables India LLP | Last Refresh: {current_time_str}
</div>
"""
st.markdown(footer_html, unsafe_allow_html=True)
# --- END OF ALTERNATIVE FOOTER ---