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
                with server_state_lock["headers"]: headers = server_state.headers
                x_forwarded_for = headers.get('X-Forwarded-For')
                if x_forwarded_for: client_ip = x_forwarded_for.split(',')[0].strip()
                else: client_ip = headers.get('X-Real-IP', 'Header_Not_Found')
            except Exception as e: logger.warning(f"Could not get IP: {e}", extra={'client_ip': 'Error', 'client_host': 'Error'}); client_ip = "Header_Error"
        else: client_ip = "Component_Missing"
        log_extra_data = {'client_ip': client_ip, 'client_host': client_host}
        logger.info("User     session started.", extra=log_extra_data)
        st.session_state.access_logged = True

# --- Call Logging Function ---
log_access_info()

# --- Rest of App Code ---
st.set_page_config(layout="wide", page_title="Eden Renewables - Project Generation Dashboard", page_icon=":bar_chart:")
st.markdown("<style>body{background-color: #f0f2f5;}</style>", unsafe_allow_html=True) # Set background color

# --- Caching Functions ---
@st.cache_data
def load_data(plant_names=None, spvs=None, years=None, quarters=None):
    """Loads data from SQLite database based on filters."""
    try: conn = sqlite3.connect(DATABASE_FILE)
    except sqlite3.Error as e: st.error(f"DB connection error: {e}"); return pd.DataFrame()
    try:
        query = "SELECT name FROM sqlite_master WHERE type='table';"
        tables_df = pd.read_sql(query, conn)
        available_tables = tables_df['name'].tolist()
    except Exception as e: st.error(f"Error reading table list: {e}"); conn.close(); return pd.DataFrame()
    if plant_names is None: conn.close(); return available_tables
    valid_plant_names = [name for name in plant_names if name in available_tables]
    if not valid_plant_names: conn.close(); return pd.DataFrame()
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
                    df[p_col] = df[p_col] / 100.0  # Convert to fraction

            df['Plant'] = plant_name
            df_list.append(df)
        except Exception as e: st.warning(f"Error reading/processing table '{plant_name}': {e}"); continue
    conn.close()
    if not df_list: return pd.DataFrame()
    try: all_data = pd.concat(df_list, ignore_index=True)
    except Exception as e: st.error(f"Error concatenating data: {e}"); return pd.DataFrame()
    if 'Months' in all_data.columns:
        all_data['Months'] = pd.to_datetime(all_data['Months'], errors='coerce')
        all_data = all_data.dropna(subset=['Months'])
    else:
         if years or (quarters and quarters != ['All']): st.warning("No 'Months' column for date filters.")
         if spvs and 'SPV' in all_data.columns: all_data = all_data[all_data['SPV'].isin(spvs)]
         elif spvs: st.warning("No 'SPV' column for SPV filter.")
         return all_data
    if spvs and 'SPV' in all_data.columns: all_data = all_data[all_data['SPV'].isin(spvs)]
    if years: all_data = all_data[all_data['Months'].dt.year.isin(years)]
    if quarters:
        actual_quarters = [q for q in quarters if q != 'All']
        if actual_quarters:
             valid_quarters = [q for q in actual_quarters if isinstance(q, int)]
             if valid_quarters: all_data = all_data[all_data['Months'].dt.quarter.isin(valid_quarters)]
    return all_data


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
        return df
    except Exception as e: st.error(f"Error loading Excel '{file_path}' sheet '{sheet_name}': {e}"); return None

# --- Helper Function to Define Formatters ---
def get_formatters(df, percent_columns=None):
    """Creates a formatter dictionary for df.style.format"""
    formatters = {}
    if percent_columns is None: percent_columns = []
    numeric_cols = df.select_dtypes(include='number').columns
    for col in numeric_cols:
        if col in percent_columns: formatters[col] = "{:.2%}"  # Percentage
        else: formatters[col] = "{:,.2f}"  # Comma-separated number
    date_cols = df.select_dtypes(include=['datetime', 'datetime64[ns]']).columns
    for col in date_cols: formatters[col] = lambda dt: dt.strftime('%b-%y') if pd.notna(dt) else 'N/A'
    return formatters

# ============================================================================== 
# Streamlit App Layout 
# ============================================================================== 
st.title("Eden Renewables - Project Generation Dashboard - UAT")
st.markdown("This dashboard provides insights into the project generation data of various plants.")
st.markdown("Select the plants, SPVs, and years to filter the data displayed below.")

# --- Data Loading --- 
with st.spinner("Loading initial data..."): 
    available_plant_names = load_data() 
    plant_capacity_data = load_excel_data(EXCEL_FILE_PATH, "Plant_Data") 
    spv_capacity_data = load_excel_data(EXCEL_FILE_PATH, "SPV_Data") 
CAPACITY_DATA_LOADED = plant_capacity_data is not None and spv_capacity_data is not None 
if not CAPACITY_DATA_LOADED: st.error("Essential capacity data from Excel missing.")

# --- Sidebar --- 
with st.sidebar: 
    if os.path.exists(LOGO_PATH): 
        try: logo_image = Image.open(LOGO_PATH); st.image(logo_image, width=150) 
        except Exception as e: st.error(f"Logo Error: {e}") 
    else: st.warning(f"Logo not found: {LOGO_PATH}") 
    st.header("Filter Options") 
    if not available_plant_names: st.warning("No plant tables found."); selected_plants = [] 
    else: selected_plants = st.multiselect("Select Plant(s):", options=available_plant_names) 
    spv_options = []; year_options = [] 
    if selected_plants: 
        with st.spinner("Loading filter options..."): 
            options_data_subset = load_data(plant_names=selected_plants) 
            if not options_data_subset.empty: 
                if 'SPV' in options_data_subset.columns: spv_options = sorted(options_data_subset['SPV'].astype(str).unique()) 
                if 'Months' in options_data_subset.columns: 
                    months_dt = pd.to_datetime(options_data_subset['Months'], errors='coerce') 
                    year_options = sorted(months_dt.dt.year.dropna().unique().astype(int), reverse=True) 
    selected_spvs = st.multiselect("Select SPV(s):", options=spv_options, help="Leave blank for all SPVs.") 
    selected_years = st.multiselect("Select Year(s):", options=year_options, help="Leave blank for all years.") 
    quarter_options = ['All', 1, 2, 3, 4] 
    selected_quarters = st.multiselect("Select Quarter(s):", options=quarter_options, default=['All']) 
    st.caption("SPV & Year options will be update based on selected Plant(s).")

# --- Main Dashboard Area --- 
if not selected_plants: st.info("👈 Select one or more plants to view data.") 
elif not CAPACITY_DATA_LOADED: st.info("Dashboard cannot display: capacity info missing.") 
else: 
    with st.spinner("Loading and filtering data..."): 
        filtered_db_data = load_data(selected_plants, selected_spvs, selected_years, selected_quarters) 
    if filtered_db_data.empty and selected_plants and (selected_spvs or selected_years or (selected_quarters != ['All'] and selected_quarters)): 
         st.warning("No DB records found matching all filters. Showing Plant info only.")

    # --- Use TABS for selected plants --- 
    if selected_plants: 
        plant_tabs = st.tabs(selected_plants) 
        for i, plant_name in enumerate(selected_plants): 
            with plant_tabs[i]: 
                st.subheader(f"Plant Overview: {plant_name}") 
                # --- PLANT GAUGE --- 
                plant_ac_capacity=0; plant_dc_capacity=0 
                plant_info=plant_capacity_data[plant_capacity_data['Plant'] == plant_name] 
                if not plant_info.empty: 
                    try: 
                        plant_ac_capacity = pd.to_numeric(plant_info['AC Capacity (MW)'].iloc[0], errors='coerce') 
                        plant_dc_capacity = pd.to_numeric(plant_info['Connected DC Capacity (MWp)'].iloc[0], errors='coerce') 
                    except Exception as e: st.warning(f"Could not read capacity for Plant '{plant_name}': {e}") 
                    plant_ac_capacity=plant_ac_capacity if pd.notna(plant_ac_capacity) else 0 
                    plant_dc_capacity=plant_dc_capacity if pd.notna(plant_dc_capacity) else 0 
                else: st.warning(f"Capacity data row not found for Plant '{plant_name}'.") 
                col_pg1, col_pg2 = st.columns(2) 
                with col_pg1: 
                    gauge_max_ac=max(1, plant_ac_capacity*1.2); 
                    fig_ac_p=go.Figure(go.Indicator(mode="gauge+number",value=plant_ac_capacity,title={'text':"AC Capacity(MW)"},gauge={'axis':{'range':[0,gauge_max_ac]},'bar':{'color':"darkorange"},'steps':[{'range':[0,gauge_max_ac],'color':"whitesmoke"}]})); 
                    fig_ac_p.update_layout(height=250, margin=dict(l=20,r=20,t=60,b=20))  # Adjusted top margin
                    st.plotly_chart(fig_ac_p, use_container_width=True,key=f"g_ac_p_{plant_name}") 
                with col_pg2: 
                    gauge_max_dc=max(1, plant_dc_capacity*1.2); 
                    fig_dc_p=go.Figure(go.Indicator(mode="gauge+number",value=plant_dc_capacity,title={'text':"DC Capacity(MWp)"},gauge={'axis':{'range':[0,gauge_max_dc]},'bar':{'color':"DodgerBlue"},'steps':[{'range':[0,gauge_max_dc],'color':"whitesmoke"}]})); 
                    fig_dc_p.update_layout(height=250, margin=dict(l=20,r=20,t=60,b=20))  # Adjusted top margin
                    st.plotly_chart(fig_dc_p, use_container_width=True,key=f"g_dc_p_{plant_name}")

                st.divider() 
                # --- Plant Level Monthly Summary --- 
                st.markdown(f"#### Monthly Summary of selected Years for {plant_name}") 
                plant_agg_data = filtered_db_data[filtered_db_data['Plant'] == plant_name].copy() 
                if plant_agg_data.empty: 
                    st.caption(f"No DB data for Plant '{plant_name}' matching filters for summary.") 
                elif 'Months' not in plant_agg_data.columns: 
                    st.warning(f"No 'Months' column for Plant '{plant_name}'.") 
                else: 
                    with st.spinner("Calculating plant summary..."): 
                        plant_agg_data['Month_Year'] = plant_agg_data['Months'].dt.strftime('%b-%y') 
                        plant_agg_data['Sort_Date'] = plant_agg_data['Months']

                        # --- Define columns to sum - CHECK THESE NAMES CAREFULLY --- 
                        cols_to_sum = ["Budget Gen (MWHr)", "Actual Gen (MWHr)"]  # Specify columns to sum

                        numeric_cols = plant_agg_data.select_dtypes(include='number').columns.tolist() 
                        cols_to_exclude = ['AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Sort_Date'] 
                        cols_to_aggregate = [col for col in numeric_cols if col not in cols_to_exclude] 
                        agg_dict = {'Sort_Date': 'min'}

                        # --- Build aggregation dictionary --- 
                        for col in cols_to_aggregate: 
                            if col in cols_to_sum: 
                                agg_dict[col] = 'sum'  # Use 'sum' for specified columns 
                            else: 
                                agg_dict[col] = 'mean'  # Use 'mean' for all others

                        if not any(c in agg_dict for c in cols_to_aggregate): 
                            st.caption(f"No data columns to summarize for Plant '{plant_name}'.") 
                        else: 
                            try: 
                                # --- Perform aggregation --- 
                                plant_summary = plant_agg_data.groupby('Month_Year', as_index=False).agg(agg_dict)

                                plant_summary = plant_summary.sort_values(by='Sort_Date').drop(columns=['Sort_Date']) 
                                plant_summary = plant_summary.rename(columns={'Month_Year': 'Month'}) 
                                percent_cols_summary = [c for c in plant_summary.columns if '%' in c or c == 'Soil Loss (%)'] 
                                formatters = get_formatters(plant_summary, percent_columns=percent_cols_summary) 
                                display_cols = ['Month'] + [c for c in plant_summary.columns if c != 'Month'] 
                                styled_plant_summary = plant_summary[display_cols].style \
                                    .format(formatters, na_rep="N/A") \
                                    .set_properties(**{'text-align': 'right'}) 
                                st.dataframe(styled_plant_summary, use_container_width=True, hide_index=True) 
                                csv_summary = plant_summary[display_cols].to_csv(index=False).encode('utf-8') 
                                st.download_button(label="Download Plant Summary as CSV", data=csv_summary, file_name=f'{plant_name}_monthly_summary.csv', mime='text/csv', key=f'download_summary_{plant_name}') 
                            except Exception as e: 
                                st.error(f"Error during plant summary aggregation: {e}")

                st.divider() 
                # --- Selected Years Summary --- 
                if selected_years: 
                    st.markdown(f"#### Summary of Selected Years for {plant_name}") 
                    selected_years_data = filtered_db_data[filtered_db_data['Plant'] == plant_name].copy() 
                    selected_years_data = selected_years_data[selected_years_data['Months'].dt.year.isin(selected_years)] 
                    if selected_years_data.empty: 
                        st.caption(f"No DB data for Plant '{plant_name}' matching selected years.") 
                    else: 
                        with st.spinner("Calculating selected years summary..."): 
                            selected_years_data['Year'] = selected_years_data['Months'].dt.year 
                            agg_dict_years = {'Year': 'first'}  # Keep the year for display
                            for col in cols_to_aggregate:
                                if col in cols_to_sum:
                                    agg_dict_years[col] = 'sum'  # Sum for specified columns
                                else:
                                    agg_dict_years[col] = 'mean'  # Average for all others

                            try:
                                years_summary = selected_years_data.groupby('Year', as_index=False).agg(agg_dict_years)
                                years_summary['Year'] = years_summary['Year'].astype(int)  # Ensure year is displayed as an integer
                                percent_cols_years_summary = [c for c in years_summary.columns if '%' in c or c == 'Soil Loss (%)']
                                formatters_years = get_formatters(years_summary, percent_columns=percent_cols_years_summary)
                                
                                # Custom formatting for the Year column to display as integer without formatting
                                formatters_years['Year'] = lambda x: f"{int(x)}"  # Display year as integer
                                
                                styled_years_summary = years_summary.style \
                                    .format(formatters_years, na_rep="N/A") \
                                    .set_properties(**{'text-align': 'right'})
                                st.dataframe(styled_years_summary, use_container_width=True, hide_index=True)
                                csv_years_summary = years_summary.to_csv(index=False).encode('utf-8')
                                st.download_button(label="Download Selected Years Summary as CSV", data=csv_years_summary, file_name=f'{plant_name}_selected_years_summary.csv', mime='text/csv', key=f'download_years_summary_{plant_name}')
                            except Exception as e:
                                st.error(f"Error during selected years summary aggregation: {e}")

                st.divider() 
                # --- SPV Section --- 
                st.markdown("#### SPV Details") 
                plant_db_data_filtered_spv = filtered_db_data[filtered_db_data['Plant'] == plant_name] 
                if 'SPV' not in plant_db_data_filtered_spv.columns: 
                    if not plant_db_data_filtered_spv.empty: st.warning(f"No 'SPV' column found for Plant '{plant_name}'.") 
                else: 
                    spvs_in_filtered_data = plant_db_data_filtered_spv['SPV'].unique() 
                    if not spvs_in_filtered_data.any(): 
                         if selected_spvs or selected_years or (selected_quarters != ['All'] and selected_quarters): st.caption(f"No SPVs for Plant '{plant_name}' match filters.") 
                         else: st.caption(f"No SPV data found for Plant '{plant_name}'.") 
                    for spv_name in spvs_in_filtered_data: 
                        with st.expander(f"View Details for SPV: {spv_name}", expanded=False): 
                            # SPV Gauges 
                            spv_ac_cap=0; spv_dc_cap=0 
                            spv_info=spv_capacity_data[spv_capacity_data['SPV'] == spv_name] 
                            if not spv_info.empty: 
                                try: 
                                    spv_ac_cap=pd.to_numeric(spv_info['AC Capacity (MW)'].iloc[0],errors='coerce') 
                                    spv_dc_cap=pd.to_numeric(spv_info['Connected DC Capacity (MWp)'].iloc[0],errors='coerce') 
                                except Exception as e: st.warning(f"Capacity read error SPV '{spv_name}': {e}") 
                                spv_ac_cap=spv_ac_cap if pd.notna(spv_ac_cap) else 0 
                                spv_dc_cap=spv_dc_cap if pd.notna(spv_dc_cap) else 0 
                            else: st.warning(f"No capacity data for SPV '{spv_name}'.") 
                            col_spv_g1, col_spv_g2 = st.columns(2) 
                            with col_spv_g1: 
                                gauge_max_sac=max(1,spv_ac_cap*1.2); 
                                fig_ac_s=go.Figure(go.Indicator(mode="gauge+number",value=spv_ac_cap,title={'text':"AC Capacity(MW)"},gauge={'axis':{'range':[0,gauge_max_sac]},'bar':{'color':"OrangeRed"},'steps':[{'range':[0,gauge_max_sac],'color':"whitesmoke"}]})); 
                                fig_ac_s.update_layout(height=200,margin=dict(l=10,r=10,t=40,b=10)); 
                                st.plotly_chart(fig_ac_s,use_container_width=True,key=f"g_ac_s_{plant_name}_{spv_name}") 
                            with col_spv_g2: 
                                gauge_max_sdc=max(1,spv_dc_cap*1.2); 
                                fig_dc_s=go.Figure(go.Indicator(mode="gauge+number",value=spv_dc_cap,title={'text':"Connected DC Capacity (MWp))"},gauge={'axis':{'range':[0,gauge_max_sac]},'bar':{'color':"CadetBlue"},'steps':[{'range':[0,gauge_max_sac],'color':"whitesmoke"}]})); 
                                fig_dc_s.update_layout(height=200,margin=dict(l=10,r=10,t=40,b=10)); 
                                st.plotly_chart(fig_dc_s,use_container_width=True,key=f"g_dc_s_{plant_name}_{spv_name}") 
                            st.markdown("---") 
                            # SPV Details Table 
                            spv_db_data_filtered_for_table = plant_db_data_filtered_spv[plant_db_data_filtered_spv['SPV'] == spv_name] 
                            if not spv_db_data_filtered_for_table.empty: 
                                db_cols_to_exclude = ['SPV', 'Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Months'] 
                                available_columns = [c for c in spv_db_data_filtered_for_table.columns if c not in db_cols_to_exclude] 
                                spv_db_data_filtered_for_table['Month'] = pd.to_datetime(spv_db_data_filtered_for_table['Months'], errors='coerce').dt.strftime('%b-%y') 
                                if 'Month' not in available_columns: available_columns.insert(0, 'Month') 
                                default_cols_count = min(len(available_columns), 6) 
                                default_columns = available_columns[:default_cols_count] 
                                st.markdown("**Monthly Database Details**") 
                                selected_columns_display = st.multiselect(f"Select columns:", options=available_columns, default=default_columns, key=f"cols_{plant_name}_{spv_name}") 
                                if selected_columns_display: 
                                    df_to_style = spv_db_data_filtered_for_table[selected_columns_display].reset_index(drop=True) 
                                    percent_cols_details = [c for c in selected_columns_display if '%' in c or c == 'Soil Loss (%)'] 
                                    formatters_details = get_formatters(df_to_style, percent_columns=percent_cols_details) 
                                    if 'Month' in df_to_style.columns: formatters_details['Month'] = None 
                                    styled_spv_details = df_to_style.style \
                                        .format(formatters_details, na_rep="N/A") \
                                        .set_properties(**{'text-align': 'right'}) \
                                        .set_properties(subset=['Month'], **{'text-align': 'left'}) 
                                    st.dataframe(styled_spv_details, use_container_width=True, hide_index=True) 
                                    # SPV Summary 
                                    st.markdown("**Summary of Displayed Columns**") 
                                    summary_data = {} 
                                    selected_columns_calc = selected_columns_display 
                                    valid_selected_columns_calc = [c for c in selected_columns_calc if c in spv_db_data_filtered_for_table.columns and c != 'Month'] 
                                    if not valid_selected_columns_calc: st.caption("No numeric columns selected.") 
                                    else: 
                                        original_spv_db_data = spv_db_data_filtered_for_table[valid_selected_columns_calc] 
                                        numeric_col_count = 0 
                                        for index, col in enumerate(valid_selected_columns_calc): 
                                            numeric_col = pd.to_numeric(original_spv_db_data[col], errors='coerce') 
                                            if not numeric_col.dropna().empty: 
                                                if numeric_col_count < 2: summary_data[col] = numeric_col.sum(); numeric_col_count += 1 
                                                else: summary_data[col] = numeric_col.mean() 
                                            elif not original_spv_db_data[col].dropna().empty: summary_data[col] = "Non-numeric" 
                                            else: summary_data[col] = None 
                                        if summary_data: 
                                            summary_df = pd.DataFrame([summary_data]) 
                                            percent_cols_summary = [c for c in summary_df.columns if '%' in c or c == 'Soil Loss (%)'] 
                                            formatters_summary = get_formatters(summary_df, percent_columns=percent_cols_summary) 
                                            styled_summary = summary_df.style \
                                                .format(formatters_summary, na_rep="N/A") \
                                                .set_properties(**{'text-align': 'right'}) 
                                            st.dataframe(styled_summary, use_container_width=True, hide_index=True) 
                                        elif valid_selected_columns_calc and all(summary_data.get(c)=="Non-numeric" or pd.isna(summary_data.get(c)) for c in valid_selected_columns_calc): st.caption("Selected columns have no numeric data.") 
                                else: st.caption("No columns selected for display.") 
                                # --- SPV Year-wise Summary --- 
                                if selected_years: 
                                    st.markdown("#### Selected Years Summary") 
                                    spv_db_data_filtered_for_years = plant_db_data_filtered_spv[plant_db_data_filtered_spv['SPV'] == spv_name] 
                                    spv_db_data_filtered_for_years = spv_db_data_filtered_for_years[spv_db_data_filtered_for_years['Months'].dt.year.isin(selected_years)] 
                                    if spv_db_data_filtered_for_years.empty: 
                                        st.caption(f"No DB data for SPV '{spv_name}' matching selected years.") 
                                    else: 
                                        with st.spinner("Calculating selected years summary for SPV..."): 
                                            spv_db_data_filtered_for_years['Year'] = spv_db_data_filtered_for_years['Months'].dt.year 
                                            agg_dict_spv_years = {'Year': 'first'}  # Keep the year for display
                                            for col in cols_to_aggregate:
                                                if col in cols_to_sum:
                                                    agg_dict_spv_years[col] = 'sum'  # Sum for specified columns
                                                else:
                                                    agg_dict_spv_years[col] = 'mean'  # Average for all others

                                            try:
                                                spv_years_summary = spv_db_data_filtered_for_years.groupby('Year', as_index=False).agg(agg_dict_spv_years)
                                                spv_years_summary['Year'] = spv_years_summary['Year'].astype(int)  # Ensure year is displayed as an integer
                                                percent_cols_spv_years_summary = [c for c in spv_years_summary.columns if '%' in c or c == 'Soil Loss (%)']
                                                formatters_spv_years = get_formatters(spv_years_summary, percent_columns=percent_cols_spv_years_summary)
                                                
                                                # Custom formatting for the Year column to display as integer without formatting
                                                formatters_spv_years['Year'] = lambda x: f"{int(x)}"  # Display year as integer
                                                
                                                styled_spv_years_summary = spv_years_summary.style \
                                                    .format(formatters_spv_years, na_rep="N/A") \
                                                    .set_properties(**{'text-align': 'right'})
                                                st.dataframe(styled_spv_years_summary, use_container_width=True, hide_index=True)
                                                csv_spv_years_summary = spv_years_summary.to_csv(index=False).encode('utf-8')
                                                st.download_button(label="Download Selected Years Summary for SPV as CSV", data=csv_spv_years_summary, file_name=f'{spv_name}_selected_years_summary.csv', mime='text/csv', key=f'download_spv_years_summary_{spv_name}')
                                            except Exception as e:
                                                st.error(f"Error during selected years summary aggregation for SPV: {e}")
                            else: st.caption(f"No monthly DB data available for SPV '{spv_name}'.")

# --- Footer --- 
st.markdown("---") 
now=datetime.datetime.now(); ct=now.strftime("%d-%b-%Y %H:%M:%S") 
cf1, cf2 = st.columns([3, 1]) 
with cf1: st.markdown(f"<span style='font-size:12px;color:grey;'>{now.year} Eden Renewables India LLP. All rights reserved.</span>", unsafe_allow_html=True) 
with cf2: st.markdown(f"<span style='font-size:12px;color:grey;float:right;'>Last Refresh: {ct}</span>", unsafe_allow_html=True) 
# --- End ---