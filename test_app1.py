# --- test_app.py (Complete Code - Plant Summary Aggregated by MMM-YY) ---

import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import os
import datetime # For Footer Timestamp and Month Formatting
from PIL import Image # For Logo
# calendar import is no longer needed for this approach

# --- Constants ---
DATABASE_FILE = 'plant_database.db' # Your SQLite database file
EXCEL_FILE_PATH = os.path.join("data", "data.xlsx") # Path to your Excel data file
LOGO_PATH = os.path.join("assets", "logo.png") # Path to your logo file (adjust filename if needed)

# Set the page configuration
st.set_page_config(layout="wide", page_title="Plant Data Dashboard")

# --- Caching Functions ---
@st.cache_data # Cache database data loading
def load_data(plant_names=None, spvs=None, years=None, quarters=None):
    """Loads data from SQLite database based on filters."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
    except sqlite3.Error as e:
        st.error(f"Database connection error: {e}")
        return pd.DataFrame()

    # Get list of all tables (assumed to be plant names)
    try:
        query = "SELECT name FROM sqlite_master WHERE type='table';"
        tables_df = pd.read_sql(query, conn)
        available_tables = tables_df['name'].tolist()
    except Exception as e:
        st.error(f"Error reading table list from database: {e}")
        conn.close()
        return pd.DataFrame()

    # If just fetching table names for initial filter
    if plant_names is None:
        conn.close()
        return available_tables # Return list of table names

    # Filter plant_names to only include tables that actually exist
    valid_plant_names = [name for name in plant_names if name in available_tables]
    if not valid_plant_names:
        # Warning displayed later if needed based on context
        conn.close()
        return pd.DataFrame() # Return empty DataFrame if no valid plants selected

    # Load data from the specified (valid) plant tables
    df_list = []
    for plant_name in valid_plant_names:
        try:
            # Use quotes around table name for safety (handles special chars like '-')
            df = pd.read_sql(f"SELECT * FROM '{plant_name}'", conn)
            df['Plant'] = plant_name  # Add column for Plant name source
            df_list.append(df)
        except pd.io.sql.DatabaseError as e:
            st.warning(f"Could not read table '{plant_name}': {e}")
            continue # Skip this table if error
        except Exception as e:
            st.warning(f"An unexpected error occurred reading table '{plant_name}': {e}")
            continue

    conn.close() # Close connection after reading data

    # Check if any data was loaded
    if not df_list:
        return pd.DataFrame() # Return empty DataFrame if no data could be loaded

    # Concatenate all dataframes
    try:
        all_data = pd.concat(df_list, ignore_index=True)
    except Exception as e:
        st.error(f"Error concatenating dataframes: {e}")
        return pd.DataFrame()

    # --- Apply Filters ---

    # Convert 'Months' safely and filter Nones
    if 'Months' in all_data.columns:
        all_data['Months'] = pd.to_datetime(all_data['Months'], errors='coerce')
        original_rows = len(all_data)
        all_data = all_data.dropna(subset=['Months'])
        # Commenting out caption for cleaner UI
        # if len(all_data) < original_rows:
        #      st.caption(f"Note: {original_rows - len(all_data)} rows with invalid 'Months' data were removed.")
    else:
         if years or (quarters and quarters != ['All']):
             st.warning("Cannot filter by Year/Quarter: 'Months' column not found in database data.")
         if spvs and 'SPV' in all_data.columns: all_data = all_data[all_data['SPV'].isin(spvs)]
         elif spvs: st.warning("Cannot filter by SPV: 'SPV' column not found in database data.")
         return all_data

    # Filter by SPV
    if spvs:
        if 'SPV' in all_data.columns: all_data = all_data[all_data['SPV'].isin(spvs)]
        else: pass

    # Filter by Year
    if years: all_data = all_data[all_data['Months'].dt.year.isin(years)]

    # Filter by Quarter (handle 'All')
    if quarters:
        actual_quarters = [q for q in quarters if q != 'All']
        if actual_quarters:
             valid_quarters = [q for q in actual_quarters if isinstance(q, int)]
             if valid_quarters: all_data = all_data[all_data['Months'].dt.quarter.isin(valid_quarters)]

    return all_data

@st.cache_data # Cache Excel data loading
def load_excel_data(file_path, sheet_name):
    """Load data from the specified sheet in the Excel file."""
    if not os.path.exists(file_path):
        st.error(f"Excel file not found at: {file_path}")
        return None
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        expected_cols = {}
        if sheet_name == "Plant_Data": expected_cols = ['Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']
        elif sheet_name == "SPV_Data": expected_cols = ['SPV', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']
        if expected_cols and not all(col in df.columns for col in expected_cols):
             missing_cols = [col for col in expected_cols if col not in df.columns]
             st.warning(f"Sheet '{sheet_name}' in {file_path} is missing expected columns: {', '.join(missing_cols)}. Check spelling and case.")
        return df
    except FileNotFoundError: st.error(f"Excel file not found at {file_path}"); return None
    except Exception as e: st.error(f"Error loading Excel file '{file_path}', sheet '{sheet_name}': {e}"); return None

# --- Formatting Function (for SPV table display) ---
def format_dataframe(df_to_format):
    """Formats DataFrame columns for display (Months, Numbers, Percentages)."""
    if df_to_format is None or df_to_format.empty: return pd.DataFrame()
    df = df_to_format.copy()
    if 'Months' in df.columns: df['Months'] = pd.to_datetime(df['Months'], errors='coerce').dt.strftime('%b-%y')
    numeric_cols = df.select_dtypes(include=['number']).columns
    for col in df.columns:
        if col == 'Months' or col in ['SPV', 'Plant']: continue
        if col in ['AC Capacity (MW)', 'Connected DC Capacity (MWp)']:
            try: df[col] = pd.to_numeric(df[col], errors='coerce').apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")
            except Exception: df[col] = "Error"
            continue
        is_percent_col = '%' in col or col == 'Soil Loss (%)'
        if col in numeric_cols:
            try:
                numeric_series = pd.to_numeric(df[col], errors='coerce')
                if is_percent_col: df[col] = numeric_series.apply(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "N/A")
                else: df[col] = numeric_series.apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")
            except Exception as e: st.warning(f"Could not format column '{col}': {e}"); df[col] = df[col].astype(str).fillna("N/A")
        elif isinstance(df[col].dtype, object):
             try:
                 numeric_series = pd.to_numeric(df[col], errors='coerce')
                 if not numeric_series.isna().all():
                     if is_percent_col: df[col] = numeric_series.apply(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else df[col].astype(str))
                     else: df[col] = numeric_series.apply(lambda x: f"{x:.2f}" if pd.notna(x) else df[col].astype(str))
                 else: df[col] = df[col].astype(str).fillna("N/A")
             except Exception: df[col] = df[col].astype(str).fillna("N/A")
    return df.fillna("N/A")

# ==============================================================================
# Streamlit App Layout
# ==============================================================================
st.title("Eden Renewables - Project Generation Dashboard - UAT")
st.markdown("This dashboard provides insights into the project generation data of various plants.")
st.markdown("Select the plants, SPVs, and years to filter the data displayed below.")
# --- Data Loading (once at the start) ---
available_plant_names = load_data()
plant_capacity_data = load_excel_data(EXCEL_FILE_PATH, "Plant_Data")
spv_capacity_data = load_excel_data(EXCEL_FILE_PATH, "SPV_Data")
CAPACITY_DATA_LOADED = plant_capacity_data is not None and spv_capacity_data is not None
if not CAPACITY_DATA_LOADED: st.error("Essential capacity data from Excel could not be loaded.")

# --- Sidebar ---
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        try: logo_image = Image.open(LOGO_PATH); st.image(logo_image, width=150)
        except Exception as e: st.error(f"Error loading logo: {e}")
    else: st.warning(f"Logo file not found at: {LOGO_PATH}")
    st.header("Filter Options")
    if not available_plant_names: st.warning("No plant tables found."); selected_plants = []
    else: selected_plants = st.multiselect("Select Plant(s):", options=available_plant_names)
    spv_options = []; year_options = []
    if selected_plants:
        options_data_subset = load_data(plant_names=selected_plants)
        if not options_data_subset.empty:
            if 'SPV' in options_data_subset.columns: spv_options = sorted(options_data_subset['SPV'].astype(str).unique())
            if 'Months' in options_data_subset.columns:
                months_dt = pd.to_datetime(options_data_subset['Months'], errors='coerce')
                year_options = sorted(months_dt.dt.year.dropna().unique().astype(int), reverse=True)
    selected_spvs = st.multiselect("Select SPV(s):", options=spv_options)
    selected_years = st.multiselect("Select Year(s):", options=year_options)
    quarter_options = ['All', 1, 2, 3, 4]
    selected_quarters = st.multiselect("Select Quarter(s):", options=quarter_options, default=['All'])

# --- Main Dashboard Area ---
if not selected_plants: st.info("👈 Select one or more plants from the sidebar to view data.")
elif not CAPACITY_DATA_LOADED: st.info("Gauges/data cannot display: capacity info missing.")
else:
    filtered_db_data = load_data(selected_plants, selected_spvs, selected_years, selected_quarters)
    if filtered_db_data.empty and selected_plants and (selected_spvs or selected_years or selected_quarters != ['All']):
         st.warning("No data found matching all selected filters.")

    # --- Loop through each SELECTED plant ---
    for plant_name in selected_plants:
        st.subheader(f"Plant: {plant_name}")

        # --- PLANT GAUGE Calculation (Uses Excel Data) ---
        plant_ac_capacity = 0; plant_dc_capacity = 0
        plant_info = plant_capacity_data[plant_capacity_data['Plant'] == plant_name]
        if not plant_info.empty:
            try:
                plant_ac_capacity = pd.to_numeric(plant_info['AC Capacity (MW)'].iloc[0], errors='coerce')
                plant_dc_capacity = pd.to_numeric(plant_info['Connected DC Capacity (MWp)'].iloc[0], errors='coerce')
            except Exception as e: st.warning(f"Could not read capacity for Plant '{plant_name}': {e}")
            plant_ac_capacity = plant_ac_capacity if pd.notna(plant_ac_capacity) else 0
            plant_dc_capacity = plant_dc_capacity if pd.notna(plant_dc_capacity) else 0
        else: st.warning(f"Capacity data row not found for Plant '{plant_name}'.")
        col_plant_g1, col_plant_g2 = st.columns(2)
        with col_plant_g1:
            gauge_max_ac = max(1, plant_ac_capacity * 1.2); fig_ac_plant = go.Figure(go.Indicator(mode="gauge+number", value=plant_ac_capacity, title={'text': f"{plant_name} AC Capacity (MW)"}, gauge={'axis': {'range': [0, gauge_max_ac]}, 'bar': {'color': "darkorange"}, 'steps': [{'range': [0, gauge_max_ac], 'color': "whitesmoke"}]})); fig_ac_plant.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20)); st.plotly_chart(fig_ac_plant, use_container_width=True, key=f"gauge_ac_plant_{plant_name}")
        with col_plant_g2:
            gauge_max_dc = max(1, plant_dc_capacity * 1.2); fig_dc_plant = go.Figure(go.Indicator(mode="gauge+number", value=plant_dc_capacity, title={'text': f"{plant_name} DC Capacity (MWp)"}, gauge={'axis': {'range': [0, gauge_max_dc]}, 'bar': {'color': "mediumpurple"}, 'steps': [{'range': [0, gauge_max_dc], 'color': "whitesmoke"}]})); fig_dc_plant.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20)); st.plotly_chart(fig_dc_plant, use_container_width=True, key=f"gauge_dc_plant_{plant_name}")

        # ==========================================================
        # --- UPDATED: Plant Level Monthly Summary (Aggregated by MMM-YY) ---
        # ==========================================================
        st.markdown("#### Plant Monthly Summary (Aggregated Across SPVs)") # Updated header

        # Filter the MAIN filtered data for THIS plant
        plant_agg_data = filtered_db_data[filtered_db_data['Plant'] == plant_name].copy()

        if plant_agg_data.empty:
            st.caption(f"No database data available for Plant '{plant_name}' matching filters for summary.")
        elif 'Months' not in plant_agg_data.columns:
            st.warning(f"Cannot create monthly summary for Plant '{plant_name}': 'Months' column missing.")
        else:
            # --- Prepare for Aggregation ---
            # Create the 'MMM-YY' grouping key AND a sort key (original date)
            plant_agg_data['Month_Year'] = plant_agg_data['Months'].dt.strftime('%b-%y')
            # Keep original date for sorting later
            plant_agg_data['Sort_Date'] = plant_agg_data['Months']

            # Define columns to sum vs average (Case-sensitive!)
            cols_to_sum = ["Budget Gen (MWHr)", "Actual Gen (MWHr)"] # MATCH YOUR COLUMN NAMES EXACTLY

            # Identify numeric columns
            numeric_cols = plant_agg_data.select_dtypes(include='number').columns.tolist()

            # Define columns to EXCLUDE from aggregation/display
            cols_to_exclude = ['AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Sort_Date'] # Exclude sort key too

            # Create the list of columns to aggregate
            cols_to_aggregate = [
                col for col in numeric_cols if col not in cols_to_exclude
            ]

            # Create the aggregation dictionary
            agg_dict = {}
            # Add min('Sort_Date') to retain the first date of the month for sorting
            agg_dict['Sort_Date'] = 'min'
            for col in cols_to_aggregate:
                if col in cols_to_sum:
                    agg_dict[col] = 'sum'
                else:
                    agg_dict[col] = 'mean' # Default to average

            # Perform the aggregation
            if not any(c in agg_dict for c in cols_to_aggregate): # Check if any data cols are left
                 st.caption(f"No data columns (excluding capacities) found to summarize for Plant '{plant_name}'.")
            else:
                try:
                    # Group by the formatted month string
                    plant_summary = plant_agg_data.groupby('Month_Year', as_index=False).agg(agg_dict)

                    # Sort chronologically using the retained 'Sort_Date'
                    plant_summary = plant_summary.sort_values(by='Sort_Date')

                    # Drop the temporary sort key column before display
                    plant_summary = plant_summary.drop(columns=['Sort_Date'])

                    # Rename 'Month_Year' to 'Month' for display
                    plant_summary = plant_summary.rename(columns={'Month_Year': 'Month'})

                    # Format numeric columns in the summary table
                    cols_in_summary = plant_summary.columns.tolist() # Get actual columns after agg
                    for col in cols_in_summary:
                        if col == 'Month': continue # Skip the grouping key

                        # Check original naming convention for percentage formatting
                        is_percent_col = '%' in col or col == 'Soil Loss (%)'

                        # Check if column exists and is numeric before formatting
                        if col in plant_summary and pd.api.types.is_numeric_dtype(plant_summary[col]):
                            try:
                                 numeric_series = pd.to_numeric(plant_summary[col], errors='coerce')
                                 if is_percent_col:
                                      # Format average percentages (*100)
                                      plant_summary[col] = numeric_series.apply(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "N/A")
                                 else:
                                      # Format sums or averages
                                      plant_summary[col] = numeric_series.apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")
                            except Exception as e:
                                 st.warning(f"Could not format summary column '{col}': {e}")
                                 plant_summary[col] = plant_summary[col].astype(str).fillna("N/A")

                    # Reorder columns: Month first, then others
                    display_cols = ['Month'] + [c for c in cols_in_summary if c != 'Month']
                    plant_summary_display = plant_summary[display_cols]

                    # Display the formatted Plant Summary table
                    st.dataframe(plant_summary_display, use_container_width=True, hide_index=True)

                except Exception as e:
                    st.error(f"An error occurred during plant summary aggregation: {e}")
                    st.dataframe(plant_agg_data.head()) # Show raw data for debugging

        st.markdown("---") # Separator before SPV details
        # ==========================================================
        # --- End of Plant Summary Section ---
        # ==========================================================


        # --- SPV Section for the current Plant ---
        plant_db_data_filtered_spv = filtered_db_data[filtered_db_data['Plant'] == plant_name]
        if 'SPV' not in plant_db_data_filtered_spv.columns: pass
        else:
            spvs_in_filtered_data = plant_db_data_filtered_spv['SPV'].unique()
            if not spvs_in_filtered_data.any() and (selected_spvs or selected_years or selected_quarters != ['All']):
                 st.caption(f"No specific SPVs found for Plant '{plant_name}' matching SPV/Year/Quarter filters.")
            # --- Loop through each relevant SPV for this Plant ---
            for spv_name in spvs_in_filtered_data:
                st.markdown(f"**SPV: {spv_name}**")
                # --- SPV GAUGE Calculation ---
                spv_ac_capacity = 0; spv_dc_capacity = 0
                spv_info = spv_capacity_data[spv_capacity_data['SPV'] == spv_name]
                if not spv_info.empty:
                    try:
                         spv_ac_capacity = pd.to_numeric(spv_info['AC Capacity (MW)'].iloc[0], errors='coerce')
                         spv_dc_capacity = pd.to_numeric(spv_info['Connected DC Capacity (MWp)'].iloc[0], errors='coerce')
                    except Exception as e: st.warning(f"Could not read capacity for SPV '{spv_name}': {e}")
                    spv_ac_capacity = spv_ac_capacity if pd.notna(spv_ac_capacity) else 0
                    spv_dc_capacity = spv_dc_capacity if pd.notna(spv_dc_capacity) else 0
                else: st.warning(f"Capacity data row not found for SPV '{spv_name}'.")
                # Display SPV Gauges
                col_spv_g1, col_spv_g2 = st.columns(2)
                with col_spv_g1: gauge_max_spv_ac = max(1, spv_ac_capacity * 1.2); fig_ac_spv = go.Figure(go.Indicator(mode="gauge+number", value=spv_ac_capacity, title={'text': f"AC Capacity (MW)"}, gauge={'axis': {'range': [0, gauge_max_spv_ac]}, 'bar': {'color': "#FF6347"}, 'steps': [{'range': [0, gauge_max_spv_ac], 'color': "whitesmoke"}]})); fig_ac_spv.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20)); st.plotly_chart(fig_ac_spv, use_container_width=True, key=f"gauge_ac_spv_{plant_name}_{spv_name}")
                with col_spv_g2: gauge_max_spv_dc = max(1, spv_dc_capacity * 1.2); fig_dc_spv = go.Figure(go.Indicator(mode="gauge+number", value=spv_dc_capacity, title={'text': f"DC Capacity (MWp)"}, gauge={'axis': {'range': [0, gauge_max_spv_dc]}, 'bar': {'color': "teal"}, 'steps': [{'range': [0, gauge_max_spv_dc], 'color': "whitesmoke"}]})); fig_dc_spv.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20)); st.plotly_chart(fig_dc_spv, use_container_width=True, key=f"gauge_dc_spv_{plant_name}_{spv_name}")

                # --- SPV Database Data Table ---
                spv_db_data_filtered_for_table = plant_db_data_filtered_spv[plant_db_data_filtered_spv['SPV'] == spv_name]
                if not spv_db_data_filtered_for_table.empty:
                    formatted_spv_data = format_dataframe(spv_db_data_filtered_for_table)
                    db_cols_to_exclude = ['SPV', 'Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']
                    available_columns = [col for col in spv_db_data_filtered_for_table.columns if col not in db_cols_to_exclude]
                    if 'Months' in available_columns: available_columns.remove('Months'); available_columns.insert(0, 'Months')
                    default_cols_count = min(len(available_columns), 6)
                    default_columns = available_columns[:default_cols_count]
                    st.markdown("**Database Details**")
                    selected_columns = st.multiselect(f"Select columns to display for {spv_name}:", options=available_columns, default=default_columns, key=f"columns_{plant_name}_{spv_name}")
                    if selected_columns:
                        st.dataframe(formatted_spv_data[selected_columns].reset_index(drop=True), use_container_width=True, hide_index=True)
                        # --- SPV Summary Section ---
                        st.markdown("**Summary of Displayed Columns**")
                        summary_data = {}
                        valid_selected_columns = [c for c in selected_columns if c in spv_db_data_filtered_for_table.columns]
                        if not valid_selected_columns: st.caption("No valid columns selected.")
                        else:
                            original_spv_db_data = spv_db_data_filtered_for_table[valid_selected_columns]
                            numeric_col_count = 0
                            for index, col in enumerate(valid_selected_columns):
                                if col == 'Months': continue
                                numeric_col = pd.to_numeric(original_spv_db_data[col], errors='coerce')
                                if not numeric_col.dropna().empty:
                                    if numeric_col_count < 2: sum_value = numeric_col.sum(); summary_data[col] = f"{sum_value:.2f}"; numeric_col_count += 1
                                    else:
                                        is_percent_col = '%' in col or col == 'Soil Loss (%)'; avg_value = numeric_col.mean()
                                        if is_percent_col: summary_data[col] = f"{avg_value * 100:.2f}%" if pd.notna(avg_value) else "N/A"
                                        else: summary_data[col] = f"{avg_value:.2f}" if pd.notna(avg_value) else "N/A"
                                elif not original_spv_db_data[col].dropna().empty: summary_data[col] = "Non-numeric"
                                else: summary_data[col] = "N/A"
                            if summary_data:
                                ordered_summary_cols = [c for c in valid_selected_columns if c in summary_data]
                                summary_df = pd.DataFrame([summary_data])[ordered_summary_cols]
                                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                            elif valid_selected_columns and all(c=='Months' or summary_data.get(c) in ["Non-numeric", "N/A"] for c in valid_selected_columns): st.caption("Selected columns have no numeric data.")
                            elif not valid_selected_columns: pass
                    else: st.caption("No columns selected for display.")
                else: st.caption(f"No database data available for SPV '{spv_name}'.")

# --- Footer ---
st.markdown("---")

st.markdown("### Additional Information")
st.markdown("This application is a UAT and will be updated with more features and data in the future.")
st.markdown("For any issues or feedback, please contact the development team.")
st.markdown("### Contact Us")
st.markdown("For any inquiries, please reach out to us at:")
st.markdown("Email: it@eden-re.com")
st.markdown("### Version History")
st.markdown("Version 1.0 - Initial release with basic functionality.")
st.markdown("Version 1.1 - Added SPV data display and summary functionality.")
st.markdown("Version 1.2 - Improved error handling and data formatting.")
st.markdown("### Known Issues")
st.markdown("1. Some data may not display correctly if the database schema changes.")
st.markdown("2. The application may not handle large datasets efficiently.")
st.markdown("3. The application is currently not optimized for mobile devices.")
st.markdown("### Future Improvements")
st.markdown("1. Improve performance with larger datasets.")
st.markdown("2. Add user authentication and authorization.")
st.markdown("3. Enhance data visualization options.")
st.markdown("4. Implement better error handling and logging.")
st.markdown("5. Add export options for data and visualizations.")
st.markdown("6. Improve user interface and experience.")
st.markdown("7. Add more detailed documentation and user guides.")


st.markdown("---")
now = datetime.datetime.now(); current_time_str = now.strftime("%d-%b-%Y %H:%M:%S")
col_footer_1, col_footer_2 = st.columns([3, 1])
with col_footer_1: st.markdown(f"<span style='font-size: 12px; color: grey;'>© {now.year} Eden Renewables India LLP - Project Generation Dashboard. All rights reserved.</span>", unsafe_allow_html=True)
with col_footer_2: st.markdown(f"<span style='font-size: 12px; color: grey; float: right;'>Last Refresh: {current_time_str}</span>", unsafe_allow_html=True)
# --- End of Script ---