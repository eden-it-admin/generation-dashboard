import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import os
import datetime  # For Footer Timestamp and Month Formatting
from PIL import Image  # For Logo
import logging  # For logging
from logging.handlers import RotatingFileHandler  # For log rotation
import socket  # For server hostname (if needed)

# --- Attempt to import streamlit-server-state ---
try:
    from streamlit_server_state import server_state, server_state_lock
    _SERVER_STATE_ENABLED = True
except ImportError:
    _SERVER_STATE_ENABLED = False
    # Define dummy objects if import fails
    class DummyServerState: headers = {}
    server_state = DummyServerState()
    # No warning here, handled in log_access_info if needed

# --- Constants ---
DATABASE_FILE = 'plant_database.db'
EXCEL_FILE_PATH = os.path.join("data", "data.xlsx")
LOGO_PATH = os.path.join("assets", "logo.png")
LOG_FILE = os.path.join("logs", "access.log")

# --- Logging Setup ---
LOG_DIR = os.path.dirname(LOG_FILE)
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - IP: %(client_ip)s - Host: %(client_host)s - Message: %(message)s')
log_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
log_handler.setFormatter(log_formatter)
logger = logging.getLogger('AppAccessLogger')
logger.setLevel(logging.INFO)
if not logger.handlers: logger.addHandler(log_handler)

# --- Function to Log Access Info ---
def log_access_info():
    if not st.session_state.get('access_logged', False):
        client_ip = "N/A"; client_host = "N/A"
        if _SERVER_STATE_ENABLED:
            try:
                # Use a copy to avoid holding the lock longer than necessary
                with server_state_lock["headers"]: headers = server_state.headers.copy()
                x_forwarded_for = headers.get('X-Forwarded-For')
                if x_forwarded_for: client_ip = x_forwarded_for.split(',')[0].strip()
                else: client_ip = headers.get('X-Real-IP', 'Header_Not_Found')
                # Try to resolve hostname (can be slow or fail)
                # try:
                #     client_host = socket.gethostbyaddr(client_ip)[0]
                # except (socket.herror, socket.gaierror, TypeError):
                #     client_host = "Resolve_Failed" # Keep it simple if resolution fails
            except Exception as e: logger.warning(f"Could not get IP/Host: {e}", extra={'client_ip': 'Error', 'client_host': 'Error'}); client_ip = "Header_Error"
        else: client_ip = "Component_Missing"; client_host="N/A" # Indicate component missing

        log_extra_data = {'client_ip': client_ip, 'client_host': client_host}
        logger.info("User session started.", extra=log_extra_data)
        st.session_state.access_logged = True


# --- Call Logging Function ---
log_access_info()

# --- Rest of App Code ---
st.set_page_config(layout="wide", page_title="Eden Renewables - Project Generation Dashboard", page_icon=":bar_chart:")
st.markdown("<style>body{background-color: #f0f2f5;}</style>", unsafe_allow_html=True) # Set background color

# --- Caching Functions ---
@st.cache_data
def load_data_base(plant_names=None, spvs=None):
    """Loads data from SQLite based ONLY on plant_names and spvs. Time filters applied later."""
    try: conn = sqlite3.connect(DATABASE_FILE)
    except sqlite3.Error as e: st.error(f"DB connection error: {e}"); return pd.DataFrame(), [] # Return empty list for available tables too

    # Get list of available tables first
    try:
        query = "SELECT name FROM sqlite_master WHERE type='table';"
        tables_df = pd.read_sql(query, conn)
        available_tables = tables_df['name'].tolist()
    except Exception as e:
        st.error(f"Error reading table list: {e}")
        conn.close()
        return pd.DataFrame(), [] # Return empty list for available tables too

    # If only table list is needed
    if plant_names is None:
        conn.close()
        return pd.DataFrame(), available_tables # Return empty DF and table list

    # Filter plant_names to only those that exist
    valid_plant_names = [name for name in plant_names if name in available_tables]
    if not valid_plant_names:
        conn.close()
        st.warning(f"Selected plants not found in database: {list(set(plant_names) - set(available_tables))}")
        return pd.DataFrame(), available_tables # Return empty DF and full table list

    # Load data for valid plants
    df_list = []
    for plant_name in valid_plant_names:
        try:
            df = pd.read_sql(f"SELECT * FROM '{plant_name}'", conn)
            # --- Ensure numeric types where expected ---
            potential_numeric_cols = ['Budget Gen (MWHr)', 'Actual Gen (MWHr)', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Soil Loss (%)']  # Add others
            for col in potential_numeric_cols:
                 if col in df.columns:
                     df[col] = pd.to_numeric(df[col], errors='coerce')

            # Convert Percentage columns stored as whole numbers (e.g., 50) to fractions (0.5)
            percent_cols_as_whole = ['Soil Loss (%)']  # Add others if needed
            for p_col in percent_cols_as_whole:
                if p_col in df.columns and pd.api.types.is_numeric_dtype(df[p_col]):
                     # Check if values seem like percentages (e.g., > 1) before dividing
                     if df[p_col].max() > 1:
                         df[p_col] = df[p_col] / 100.0

            df['Plant'] = plant_name
            df_list.append(df)
        except pd.io.sql.DatabaseError as db_err:
             # Handle specific case where table might exist but is empty or unreadable
             if "no such table" in str(db_err):
                 st.warning(f"Table '{plant_name}' reported as missing or unreadable by SQLite.")
             else:
                 st.warning(f"Error reading table '{plant_name}': {db_err}")
             continue # Skip this table
        except Exception as e:
             st.warning(f"Error processing table '{plant_name}': {e}");
             continue # Skip this table

    conn.close()

    if not df_list: return pd.DataFrame(), available_tables

    try: all_data = pd.concat(df_list, ignore_index=True)
    except Exception as e: st.error(f"Error concatenating data: {e}"); return pd.DataFrame(), available_tables

    # --- Basic Date Conversion ---
    if 'Months' in all_data.columns:
        all_data['Months'] = pd.to_datetime(all_data['Months'], errors='coerce')
        all_data = all_data.dropna(subset=['Months']) # Drop rows where date conversion failed
    else:
        st.warning("Critical 'Months' column missing in the loaded data. Date filtering will not work.")

    # --- Apply SPV Filter (if provided) ---
    if spvs and 'SPV' in all_data.columns:
        all_data = all_data[all_data['SPV'].isin(spvs)]
    elif spvs:
        st.warning("SPV filter provided, but 'SPV' column not found in the data.")

    # --- Return the base loaded data and the list of available tables ---
    return all_data, available_tables


@st.cache_data
def load_excel_data(file_path, sheet_name):
    """Load data from the specified sheet in the Excel file."""
    if not os.path.exists(file_path): st.error(f"Excel file not found: {file_path}"); return None
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        expected_cols = {}
        if sheet_name == "Plant_Data": expected_cols = ['Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']
        elif sheet_name == "SPV_Data": expected_cols = ['SPV', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']
        if expected_cols and not all(col in df.columns for col in expected_cols):
             missing = [c for c in expected_cols if c not in df.columns]
             st.warning(f"Sheet '{sheet_name}' missing expected columns: {missing}.")
        # Ensure capacity columns are numeric
        if sheet_name in ["Plant_Data", "SPV_Data"]:
             for cap_col in ['AC Capacity (MW)', 'Connected DC Capacity (MWp)']:
                 if cap_col in df.columns:
                     df[cap_col] = pd.to_numeric(df[cap_col], errors='coerce')
        return df
    except Exception as e: st.error(f"Error loading Excel '{file_path}' sheet '{sheet_name}': {e}"); return None

# --- Helper Function to Define Formatters ---
def get_formatters(df, percent_columns=None):
    """Creates a formatter dictionary for df.style.format"""
    formatters = {}
    if percent_columns is None: percent_columns = []
    numeric_cols = df.select_dtypes(include='number').columns
    for col in numeric_cols:
        # Special handling for 'Year' column - display as integer
        if col == 'Year':
             formatters[col] = lambda x: f"{int(x):,}" if pd.notna(x) else 'N/A' # Integer, no decimals
        elif col in percent_columns: formatters[col] = "{:.2%}"  # Percentage
        else: formatters[col] = "{:,.2f}"  # Comma-separated number with 2 decimals
    date_cols = df.select_dtypes(include=['datetime', 'datetime64[ns]']).columns
    for col in date_cols: formatters[col] = lambda dt: dt.strftime('%b-%y') if pd.notna(dt) else 'N/A'
    return formatters

# ==============================================================================
# Streamlit App Layout
# ==============================================================================
st.title("Eden Renewables - Project Generation Dashboard - UAT")
st.markdown("This dashboard provides insights into the project generation data of various plants.")
st.markdown("Select the plants, SPVs, and time filters to explore the data.")

# --- Initial Data Loading (only available plants for sidebar) ---
with st.spinner("Loading initial data..."):
    _, available_plant_names = load_data_base() # Get only the list of plants initially
    plant_capacity_data = load_excel_data(EXCEL_FILE_PATH, "Plant_Data")
    spv_capacity_data = load_excel_data(EXCEL_FILE_PATH, "SPV_Data")
CAPACITY_DATA_LOADED = plant_capacity_data is not None and spv_capacity_data is not None
if not CAPACITY_DATA_LOADED: st.error("Essential capacity data from Excel missing. Gauges will not display correctly.")

# --- Sidebar ---
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        try: logo_image = Image.open(LOGO_PATH); st.image(logo_image, width=150)
        except Exception as e: st.error(f"Logo Error: {e}")
    else: st.warning(f"Logo not found: {LOGO_PATH}")
    st.header("Filter Options")
    if not available_plant_names:
        st.warning("No plant tables found in the database."); selected_plants = []
    else:
        selected_plants = st.multiselect("Select Plant(s):", options=available_plant_names)

    # --- Dynamic SPV and Year Options based on selected plants ---
    spv_options = []
    year_options = [] # Initialize year options
    temp_base_data_for_options = pd.DataFrame() # Initialize empty df

    if selected_plants:
        with st.spinner("Loading filter options..."):
            # Load minimal data just to get SPV and Year options
            temp_base_data_for_options, _ = load_data_base(plant_names=selected_plants)

            if not temp_base_data_for_options.empty:
                if 'SPV' in temp_base_data_for_options.columns:
                    spv_options = sorted(temp_base_data_for_options['SPV'].astype(str).unique())
                if 'Months' in temp_base_data_for_options.columns:
                    months_dt = pd.to_datetime(temp_base_data_for_options['Months'], errors='coerce').dropna()
                    if not months_dt.empty:
                         numeric_years = sorted(months_dt.dt.year.unique().astype(int), reverse=True)
                         year_options = ['All'] + numeric_years # Add 'All' option here
                    else:
                         year_options = ['All'] # Default if no valid dates
                else:
                     year_options = ['All'] # Default if no 'Months' column
            else:
                 year_options = ['All'] # Default if no data loaded

    selected_spvs = st.multiselect("Select SPV(s):", options=spv_options, help="Leave blank for all SPVs in selected plants.")

    # Set default for year filter to 'All' if available
    default_year = ['All'] if 'All' in year_options else []
    selected_years_input = st.multiselect("Select Year(s):", options=year_options, default=default_year, help="'All' shows data for every year.")

    quarter_options = ['All', 1, 2, 3, 4]
    selected_quarters_input = st.multiselect("Select Quarter(s):", options=quarter_options, default=['All'])
    st.caption("SPV & Year options updated based on selected Plant(s).")


# --- Determine Active Filters ---
# Handle 'All' selection for years
apply_year_filter = selected_years_input and 'All' not in selected_years_input
actual_years_filter = [y for y in selected_years_input if isinstance(y, int)] if apply_year_filter else []

# Handle 'All' selection for quarters
apply_quarter_filter = selected_quarters_input and 'All' not in selected_quarters_input
actual_quarters_filter = [q for q in selected_quarters_input if isinstance(q, int)] if apply_quarter_filter else []


# --- Main Dashboard Area ---
if not selected_plants: st.info("👈 Select one or more plants to view data.")
# No need to check CAPACITY_DATA_LOADED here, handled in gauge display
else:
    # --- Load Base Data based on Plant & SPV filters ---
    with st.spinner("Loading data based on Plant/SPV filters..."):
        # Pass selected_spvs (can be empty list)
        base_db_data, _ = load_data_base(selected_plants, selected_spvs)

    # --- Apply Time Filters (Year/Quarter) to create filtered_db_data ---
    filtered_db_data = base_db_data.copy() # Start with the base data

    if not filtered_db_data.empty and 'Months' in filtered_db_data.columns:
        if apply_year_filter:
            filtered_db_data = filtered_db_data[filtered_db_data['Months'].dt.year.isin(actual_years_filter)]
        if apply_quarter_filter:
             filtered_db_data = filtered_db_data[filtered_db_data['Months'].dt.quarter.isin(actual_quarters_filter)]
    elif (apply_year_filter or apply_quarter_filter) and 'Months' not in filtered_db_data.columns:
         st.warning("Cannot apply Year/Quarter filters: 'Months' column missing.")

    # --- Display Warnings Based on Data Availability ---
    if base_db_data.empty and selected_plants:
         # This means no data even for selected plants/spvs before time filters
         st.warning("No database records found for the selected Plant(s) and SPV(s).")
         # Set filtered data also to empty to avoid errors downsteam
         filtered_db_data = pd.DataFrame()
    elif filtered_db_data.empty and (apply_year_filter or apply_quarter_filter):
         # This means base data existed, but time filters removed everything
         st.warning("No database records found matching all filters (Plant, SPV, Year, Quarter). Showing Plant info and All Years Summary only.")


    # --- Use TABS for selected plants ---
    if selected_plants:
        plant_tabs = st.tabs(selected_plants)
        for i, plant_name in enumerate(selected_plants):
            with plant_tabs[i]:
                st.subheader(f"Plant Overview: {plant_name}")

                # --- Filter dataframes for the current plant ---
                # Use base_db_data for calculations independent of time filters (like All Years Summary)
                plant_base_data = base_db_data[base_db_data['Plant'] == plant_name].copy()
                # Use filtered_db_data for displays affected by time filters (Monthly, Selected Years, SPV Details)
                plant_filtered_data = filtered_db_data[filtered_db_data['Plant'] == plant_name].copy()

                # --- PLANT GAUGE (Uses Excel Capacity Data) ---
                plant_ac_capacity=0; plant_dc_capacity=0
                if CAPACITY_DATA_LOADED:
                    plant_info=plant_capacity_data[plant_capacity_data['Plant'] == plant_name]
                    if not plant_info.empty:
                        # Already converted to numeric in load_excel_data
                        plant_ac_capacity = plant_info['AC Capacity (MW)'].iloc[0]
                        plant_dc_capacity = plant_info['Connected DC Capacity (MWp)'].iloc[0]
                        plant_ac_capacity=plant_ac_capacity if pd.notna(plant_ac_capacity) else 0
                        plant_dc_capacity=plant_dc_capacity if pd.notna(plant_dc_capacity) else 0
                    else: st.warning(f"Capacity data row not found for Plant '{plant_name}' in Excel.")
                else: st.warning("Plant capacity Excel data not loaded.")

                col_pg1, col_pg2 = st.columns(2)
                with col_pg1:
                    gauge_max_ac=max(1, plant_ac_capacity*1.2)
                    fig_ac_p=go.Figure(go.Indicator(mode="gauge+number",value=plant_ac_capacity,title={'text':"AC Capacity (MW)"},gauge={'axis':{'range':[0,gauge_max_ac]},'bar':{'color':"darkorange"},'steps':[{'range':[0,gauge_max_ac],'color':"whitesmoke"}]}))
                    fig_ac_p.update_layout(height=250, margin=dict(l=20,r=20,t=60,b=20))
                    st.plotly_chart(fig_ac_p, use_container_width=True,key=f"g_ac_p_{plant_name}")
                with col_pg2:
                    gauge_max_dc=max(1, plant_dc_capacity*1.2)
                    fig_dc_p=go.Figure(go.Indicator(mode="gauge+number",value=plant_dc_capacity,title={'text':"DC Capacity (MWp)"},gauge={'axis':{'range':[0,gauge_max_dc]},'bar':{'color':"DodgerBlue"},'steps':[{'range':[0,gauge_max_dc],'color':"whitesmoke"}]}))
                    fig_dc_p.update_layout(height=250, margin=dict(l=20,r=20,t=60,b=20))
                    st.plotly_chart(fig_dc_p, use_container_width=True,key=f"g_dc_p_{plant_name}")

                st.divider()
                # --- Plant Level Monthly Summary (uses TIME-FILTERED data) ---
                st.markdown(f"#### Monthly Summary (Based on Filters) for {plant_name}")
                # Use plant_filtered_data here
                if plant_filtered_data.empty:
                    st.caption(f"No DB data for Plant '{plant_name}' matching current filters for monthly summary.")
                elif 'Months' not in plant_filtered_data.columns:
                    st.warning(f"No 'Months' column for Plant '{plant_name}' to display monthly summary.")
                else:
                    with st.spinner("Calculating monthly summary..."):
                        monthly_summary_data = plant_filtered_data.copy()
                        monthly_summary_data['Month_Year'] = monthly_summary_data['Months'].dt.strftime('%b-%y')
                        monthly_summary_data['Sort_Date'] = monthly_summary_data['Months']

                        # --- Define aggregation logic (consistent across summaries) ---
                        cols_to_sum = ["Budget Gen (MWHr)", "Actual Gen (MWHr)"]
                        numeric_cols = monthly_summary_data.select_dtypes(include='number').columns.tolist()
                        # Exclude capacity cols if they exist, Sort_Date, and potentially Year if grouped by Year
                        cols_to_exclude_agg = ['AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Sort_Date', 'Year']
                        cols_to_aggregate = [col for col in numeric_cols if col not in cols_to_exclude_agg]
                        agg_dict_monthly = {'Sort_Date': 'min'} # Base dict

                        for col in cols_to_aggregate:
                            if col in cols_to_sum: agg_dict_monthly[col] = 'sum'
                            else: agg_dict_monthly[col] = 'mean'

                        if not any(c in agg_dict_monthly for c in cols_to_aggregate):
                            st.caption(f"No data columns to summarize monthly for Plant '{plant_name}'.")
                        else:
                            try:
                                plant_summary = monthly_summary_data.groupby('Month_Year', as_index=False).agg(agg_dict_monthly)
                                plant_summary = plant_summary.sort_values(by='Sort_Date').drop(columns=['Sort_Date'])
                                plant_summary = plant_summary.rename(columns={'Month_Year': 'Month'})
                                percent_cols_summary = [c for c in plant_summary.columns if '%' in c or c == 'Soil Loss (%)']
                                formatters = get_formatters(plant_summary, percent_columns=percent_cols_summary)
                                display_cols = ['Month'] + [c for c in plant_summary.columns if c != 'Month']
                                styled_plant_summary = plant_summary[display_cols].style \
                                    .format(formatters, na_rep="N/A") \
                                    .set_properties(**{'text-align': 'right'}) \
                                    .set_properties(subset=['Month'], **{'text-align': 'left'}) # Align Month left
                                st.dataframe(styled_plant_summary, use_container_width=True, hide_index=True)
                                csv_summary = plant_summary[display_cols].to_csv(index=False).encode('utf-8')
                                st.download_button(label="Download Monthly Summary as CSV", data=csv_summary, file_name=f'{plant_name}_monthly_summary_filtered.csv', mime='text/csv', key=f'download_monthly_summary_{plant_name}')
                            except Exception as e:
                                st.error(f"Error during monthly summary aggregation: {e}")
                                logging.exception(f"Aggregation error for {plant_name} monthly summary") # Log detailed error

                st.divider()
                # --- NEW: All Years Summary (uses BASE data - NOT time-filtered) ---
                st.markdown(f"#### All Years Summary for {plant_name}")
                # Use plant_base_data here
                if plant_base_data.empty:
                     st.caption(f"No DB data available for Plant '{plant_name}' to calculate All Years Summary.")
                elif 'Months' not in plant_base_data.columns:
                     st.warning(f"No 'Months' column for Plant '{plant_name}' to summarize by year.")
                else:
                    with st.spinner("Calculating all years summary..."):
                        all_years_data = plant_base_data.copy()
                        all_years_data['Year'] = all_years_data['Months'].dt.year

                        # Reuse aggregation logic setup from monthly summary
                        agg_dict_all_years = {} # Start fresh dict
                        for col in cols_to_aggregate: # Use same list of columns to aggregate
                            if col in cols_to_sum: agg_dict_all_years[col] = 'sum'
                            else: agg_dict_all_years[col] = 'mean'

                        # Check if there's anything to aggregate
                        if not agg_dict_all_years:
                            st.caption(f"No data columns to summarize across all years for Plant '{plant_name}'.")
                        else:
                            try:
                                all_years_summary = all_years_data.groupby('Year', as_index=False).agg(agg_dict_all_years)
                                all_years_summary = all_years_summary.sort_values(by='Year')
                                all_years_summary['Year'] = all_years_summary['Year'].astype(int)

                                percent_cols_all_years = [c for c in all_years_summary.columns if '%' in c or c == 'Soil Loss (%)']
                                formatters_all_years = get_formatters(all_years_summary, percent_columns=percent_cols_all_years)

                                # Ensure 'Year' column is included for display
                                display_cols_all_years = ['Year'] + [c for c in all_years_summary.columns if c != 'Year']

                                styled_all_years_summary = all_years_summary[display_cols_all_years].style \
                                    .format(formatters_all_years, na_rep="N/A") \
                                    .set_properties(**{'text-align': 'right'}) \
                                    .set_properties(subset=['Year'], **{'text-align': 'left'}) # Align Year left
                                st.dataframe(styled_all_years_summary, use_container_width=True, hide_index=True)
                                csv_all_years = all_years_summary[display_cols_all_years].to_csv(index=False).encode('utf-8')
                                st.download_button(label="Download All Years Summary as CSV", data=csv_all_years, file_name=f'{plant_name}_all_years_summary.csv', mime='text/csv', key=f'download_all_years_{plant_name}')
                            except Exception as e:
                                st.error(f"Error during all years summary aggregation: {e}")
                                logging.exception(f"Aggregation error for {plant_name} all years summary")

                st.divider()
                # --- Selected Years Summary (uses TIME-FILTERED data, only shown if specific years are selected) ---
                if apply_year_filter: # Only show this section if specific years were selected
                    st.markdown(f"#### Summary of Selected Years ({', '.join(map(str, actual_years_filter))}) for {plant_name}")
                    # Use plant_filtered_data here
                    selected_years_data = plant_filtered_data.copy() # Already filtered by year

                    if selected_years_data.empty:
                        st.caption(f"No DB data for Plant '{plant_name}' matching selected years.")
                    elif 'Months' not in selected_years_data.columns:
                        st.warning(f"No 'Months' column for Plant '{plant_name}'.")
                    else:
                        with st.spinner("Calculating selected years summary..."):
                            selected_years_data['Year'] = selected_years_data['Months'].dt.year

                            # Reuse aggregation logic
                            agg_dict_sel_years = {}
                            for col in cols_to_aggregate:
                                if col in cols_to_sum: agg_dict_sel_years[col] = 'sum'
                                else: agg_dict_sel_years[col] = 'mean'

                            if not agg_dict_sel_years:
                                st.caption(f"No data columns to summarize for selected years for Plant '{plant_name}'.")
                            else:
                                try:
                                    years_summary = selected_years_data.groupby('Year', as_index=False).agg(agg_dict_sel_years)
                                    years_summary = years_summary.sort_values(by='Year')
                                    years_summary['Year'] = years_summary['Year'].astype(int)

                                    percent_cols_years_summary = [c for c in years_summary.columns if '%' in c or c == 'Soil Loss (%)']
                                    formatters_years = get_formatters(years_summary, percent_columns=percent_cols_years_summary)

                                    display_cols_sel_years = ['Year'] + [c for c in years_summary.columns if c != 'Year']
                                    styled_years_summary = years_summary[display_cols_sel_years].style \
                                        .format(formatters_years, na_rep="N/A") \
                                        .set_properties(**{'text-align': 'right'}) \
                                        .set_properties(subset=['Year'], **{'text-align': 'left'})
                                    st.dataframe(styled_years_summary, use_container_width=True, hide_index=True)
                                    csv_years_summary = years_summary[display_cols_sel_years].to_csv(index=False).encode('utf-8')
                                    st.download_button(label="Download Selected Years Summary as CSV", data=csv_years_summary, file_name=f'{plant_name}_selected_years_summary.csv', mime='text/csv', key=f'download_years_summary_{plant_name}')
                                except Exception as e:
                                    st.error(f"Error during selected years summary aggregation: {e}")
                                    logging.exception(f"Aggregation error for {plant_name} selected years summary")
                # else: (Optional) Add a note if no specific years are selected
                #    st.caption("Select specific years in the filter to see a summary just for those years.")


                st.divider()
                # --- SPV Section (uses TIME-FILTERED data) ---
                st.markdown("#### SPV Details (Based on Filters)")
                # Use plant_filtered_data here
                if 'SPV' not in plant_filtered_data.columns:
                    if not plant_filtered_data.empty: st.warning(f"No 'SPV' column found for Plant '{plant_name}'.")
                    # No need for else, if plant_filtered_data is empty, the next check handles it
                else:
                    spvs_in_filtered_data = sorted(plant_filtered_data['SPV'].unique())
                    if not spvs_in_filtered_data:
                         # Check if filters might be the reason
                         if apply_year_filter or apply_quarter_filter or selected_spvs:
                              st.caption(f"No SPVs for Plant '{plant_name}' match the current filters.")
                         elif not plant_base_data.empty and 'SPV' in plant_base_data.columns and plant_base_data['SPV'].nunique() > 0:
                             # Base data had SPVs, but maybe they were filtered out by SPV multiselect?
                             st.caption(f"No SPVs selected or found for Plant '{plant_name}' after applying SPV filter.")
                         else:
                             st.caption(f"No SPV data found in the database for Plant '{plant_name}'.")

                    for spv_name in spvs_in_filtered_data:
                        # Get SPV specific data from the already time-filtered plant data
                        spv_filtered_data = plant_filtered_data[plant_filtered_data['SPV'] == spv_name]

                        with st.expander(f"View Details for SPV: {spv_name}", expanded=False):
                            # SPV Gauges (Uses Excel Capacity Data)
                            spv_ac_cap=0; spv_dc_cap=0
                            if CAPACITY_DATA_LOADED:
                                spv_info=spv_capacity_data[spv_capacity_data['SPV'] == spv_name]
                                if not spv_info.empty:
                                    # Already numeric
                                    spv_ac_cap=spv_info['AC Capacity (MW)'].iloc[0]
                                    spv_dc_cap=spv_info['Connected DC Capacity (MWp)'].iloc[0]
                                    spv_ac_cap=spv_ac_cap if pd.notna(spv_ac_cap) else 0
                                    spv_dc_cap=spv_dc_cap if pd.notna(spv_dc_cap) else 0
                                else: st.warning(f"No capacity data found for SPV '{spv_name}' in Excel.")
                            else: st.warning("SPV capacity Excel data not loaded.")

                            col_spv_g1, col_spv_g2 = st.columns(2)
                            with col_spv_g1:
                                gauge_max_sac=max(1,spv_ac_cap*1.2)
                                fig_ac_s=go.Figure(go.Indicator(mode="gauge+number",value=spv_ac_cap,title={'text':"AC Capacity(MW)"},gauge={'axis':{'range':[0,gauge_max_sac]},'bar':{'color':"OrangeRed"},'steps':[{'range':[0,gauge_max_sac],'color':"whitesmoke"}]}))
                                fig_ac_s.update_layout(height=200,margin=dict(l=10,r=10,t=40,b=10))
                                st.plotly_chart(fig_ac_s,use_container_width=True,key=f"g_ac_s_{plant_name}_{spv_name}")
                            with col_spv_g2:
                                gauge_max_sdc=max(1,spv_dc_cap*1.2)
                                # *** POTENTIAL BUG FIX: Use gauge_max_sdc for range in DC gauge ***
                                fig_dc_s=go.Figure(go.Indicator(mode="gauge+number",value=spv_dc_cap,title={'text':"Connected DC Capacity (MWp)"},gauge={'axis':{'range':[0,gauge_max_sdc]},'bar':{'color':"CadetBlue"},'steps':[{'range':[0,gauge_max_sdc],'color':"whitesmoke"}]}))
                                fig_dc_s.update_layout(height=200,margin=dict(l=10,r=10,t=40,b=10))
                                st.plotly_chart(fig_dc_s,use_container_width=True,key=f"g_dc_s_{plant_name}_{spv_name}")
                            st.markdown("---")

                            # SPV Details Table (uses TIME-FILTERED data for this SPV)
                            if not spv_filtered_data.empty and 'Months' in spv_filtered_data.columns:
                                spv_table_data = spv_filtered_data.copy()
                                spv_table_data['Month'] = spv_table_data['Months'].dt.strftime('%b-%y')
                                spv_table_data = spv_table_data.sort_values(by='Months') # Sort before display

                                db_cols_to_exclude_display = ['SPV', 'Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Months']
                                available_columns = ['Month'] + [c for c in spv_table_data.columns if c not in db_cols_to_exclude_display and c != 'Month']

                                default_cols_count = min(len(available_columns), 6)
                                default_columns = available_columns[:default_cols_count]

                                st.markdown("**Monthly Database Details (Filtered)**")
                                selected_columns_display = st.multiselect(f"Select columns:", options=available_columns, default=default_columns, key=f"cols_{plant_name}_{spv_name}")

                                if selected_columns_display:
                                    df_to_style = spv_table_data[selected_columns_display].reset_index(drop=True)
                                    percent_cols_details = [c for c in selected_columns_display if '%' in c or c == 'Soil Loss (%)']
                                    formatters_details = get_formatters(df_to_style, percent_columns=percent_cols_details)
                                    # Ensure Month formatting is handled by get_formatters or override if needed
                                    # if 'Month' in df_to_style.columns: formatters_details['Month'] = None # Let default handle or strftime

                                    styled_spv_details = df_to_style.style \
                                        .format(formatters_details, na_rep="N/A") \
                                        .set_properties(**{'text-align': 'right'}) \
                                        .set_properties(subset=['Month'], **{'text-align': 'left'})
                                    st.dataframe(styled_spv_details, use_container_width=True, hide_index=True)

                                    # SPV Summary (Based on displayed columns in the FILTERED table above)
                                    st.markdown("**Summary of Displayed Columns (Based on Filtered Data Above)**")
                                    summary_data = {}
                                    numeric_cols_in_selection = df_to_style.select_dtypes(include='number').columns
                                    cols_to_sum_spv = ["Budget Gen (MWHr)", "Actual Gen (MWHr)"] # Define sums for SPV level too

                                    for col in numeric_cols_in_selection:
                                         numeric_col_data = pd.to_numeric(df_to_style[col], errors='coerce')
                                         if not numeric_col_data.dropna().empty:
                                             # Sum specific generation columns, average others
                                             if col in cols_to_sum_spv:
                                                 summary_data[col] = numeric_col_data.sum()
                                             else:
                                                 summary_data[col] = numeric_col_data.mean()
                                         else:
                                             summary_data[col] = None # Or "N/A" if preferred

                                    if summary_data:
                                        summary_df = pd.DataFrame([summary_data])
                                        percent_cols_summary_spv = [c for c in summary_df.columns if '%' in c or c == 'Soil Loss (%)']
                                        formatters_summary_spv = get_formatters(summary_df, percent_columns=percent_cols_summary_spv)
                                        styled_summary = summary_df.style \
                                            .format(formatters_summary_spv, na_rep="N/A") \
                                            .set_properties(**{'text-align': 'right'})
                                        st.dataframe(styled_summary, use_container_width=True, hide_index=True)
                                    else:
                                        st.caption("No numeric columns selected or selected columns have no numeric data.")
                                else: st.caption("No columns selected for display.")

                                # --- SPV Selected Year-wise Summary (uses TIME-FILTERED data) ---
                                if apply_year_filter: # Only show if specific years selected
                                    st.markdown("#### Selected Years Summary for SPV")
                                    spv_years_data = spv_filtered_data.copy() # Already filtered by year and SPV

                                    if spv_years_data.empty:
                                        st.caption(f"No DB data for SPV '{spv_name}' matching selected years.")
                                    elif 'Months' not in spv_years_data.columns:
                                         st.warning(f"No 'Months' column for SPV '{spv_name}'.")
                                    else:
                                        with st.spinner("Calculating selected years summary for SPV..."):
                                            spv_years_data['Year'] = spv_years_data['Months'].dt.year

                                            # Reuse aggregation logic
                                            agg_dict_spv_years = {}
                                            for col in cols_to_aggregate: # Use the main cols_to_aggregate list
                                                if col in cols_to_sum: agg_dict_spv_years[col] = 'sum'
                                                else: agg_dict_spv_years[col] = 'mean'

                                            if not agg_dict_spv_years:
                                                 st.caption(f"No data columns to summarize yearly for SPV '{spv_name}'.")
                                            else:
                                                 try:
                                                     spv_years_summary = spv_years_data.groupby('Year', as_index=False).agg(agg_dict_spv_years)
                                                     spv_years_summary = spv_years_summary.sort_values(by='Year')
                                                     spv_years_summary['Year'] = spv_years_summary['Year'].astype(int)

                                                     percent_cols_spv_years = [c for c in spv_years_summary.columns if '%' in c or c == 'Soil Loss (%)']
                                                     formatters_spv_years = get_formatters(spv_years_summary, percent_columns=percent_cols_spv_years)

                                                     display_cols_spv_years = ['Year'] + [c for c in spv_years_summary.columns if c != 'Year']
                                                     styled_spv_years_summary = spv_years_summary[display_cols_spv_years].style \
                                                         .format(formatters_spv_years, na_rep="N/A") \
                                                         .set_properties(**{'text-align': 'right'}) \
                                                         .set_properties(subset=['Year'], **{'text-align': 'left'})
                                                     st.dataframe(styled_spv_years_summary, use_container_width=True, hide_index=True)
                                                     csv_spv_years_summary = spv_years_summary[display_cols_spv_years].to_csv(index=False).encode('utf-8')
                                                     st.download_button(label="Download SPV Selected Years Summary as CSV", data=csv_spv_years_summary, file_name=f'{plant_name}_{spv_name}_selected_years_summary.csv', mime='text/csv', key=f'download_spv_years_summary_{plant_name}_{spv_name}')
                                                 except Exception as e:
                                                     st.error(f"Error during SPV selected years summary aggregation: {e}")
                                                     logging.exception(f"Aggregation error for {plant_name}/{spv_name} selected years summary")
                            elif spv_filtered_data.empty:
                                 st.caption(f"No monthly DB data available for SPV '{spv_name}' matching the current filters.")
                            else: # Data exists but no 'Months' column
                                 st.warning(f"Data for SPV '{spv_name}' is missing the 'Months' column, cannot display monthly details.")


# --- Footer ---
st.markdown("---")
now=datetime.datetime.now(); ct=now.strftime("%d-%b-%Y %H:%M:%S")
cf1, cf2 = st.columns([3, 1])
with cf1: st.markdown(f"<span style='font-size:12px;color:grey;'>© {now.year} Eden Renewables India LLP. All rights reserved.</span>", unsafe_allow_html=True)
with cf2: st.markdown(f"<span style='font-size:12px;color:grey;float:right;'>Last Refresh: {ct}</span>", unsafe_allow_html=True)
# --- End ---