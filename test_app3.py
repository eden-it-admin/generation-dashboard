# --- test_app.py (Complete Code - UI/UX Enhancements Applied) ---

import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import os
import datetime # For Footer Timestamp and Month Formatting
from PIL import Image # For Logo
# calendar import no longer needed directly, strftime handles format

# --- Constants ---
DATABASE_FILE = 'plant_database.db' # Your SQLite database file
EXCEL_FILE_PATH = os.path.join("data", "data.xlsx") # Path to your Excel data file
LOGO_PATH = os.path.join("assets", "logo.png") # Path to your logo file (adjust filename if needed)

# Set the page configuration
st.set_page_config(layout="wide", page_title="Eden Renewables - Project Generation Dashboard", initial_sidebar_state="expanded", page_icon=":bar_chart:")

# --- Caching Functions ---
@st.cache_data # Cache database data loading
def load_data(plant_names=None, spvs=None, years=None, quarters=None):
    """Loads data from SQLite database based on filters."""
    try: conn = sqlite3.connect(DATABASE_FILE)
    except sqlite3.Error as e: st.error(f"Database connection error: {e}"); return pd.DataFrame()
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
            # Convert numeric/percentage cols right after reading
            potential_numeric_cols = ['Budget Gen (MWHr)', 'Actual Gen (MWHr)', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Soil Loss (%)'] # Add others
            for col in potential_numeric_cols:
                 if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
            percent_cols_as_whole = ['Soil Loss (%)'] # Add others if stored as 50 for 50%
            for p_col in percent_cols_as_whole:
                if p_col in df.columns and pd.api.types.is_numeric_dtype(df[p_col]): df[p_col] = df[p_col] / 100.0
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

@st.cache_data # Cache Excel data loading
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
        if col in percent_columns: formatters[col] = "{:.2%}" # Percentage
        else: formatters[col] = "{:,.2f}" # Comma-separated number
    date_cols = df.select_dtypes(include=['datetime', 'datetime64[ns]']).columns
    for col in date_cols: formatters[col] = lambda dt: dt.strftime('%b-%y') if pd.notna(dt) else 'N/A'
    return formatters

# ==============================================================================
# Streamlit App Layout
# ==============================================================================
st.title("Eden Renewables - Project Generation Dashboard - UAT")
st.markdown("### Generation Data Overview") # Title
st.markdown("This dashboard provides an overview of generation data for selected plants and SPVs. Use the filters in the sidebar to customize your view.")

# --- Data Loading ---
# Wrap initial data loading in spinners for better feedback
with st.spinner("Loading initial data..."):
    available_plant_names = load_data()
    plant_capacity_data = load_excel_data(EXCEL_FILE_PATH, "Plant_Data")
    spv_capacity_data = load_excel_data(EXCEL_FILE_PATH, "SPV_Data")

CAPACITY_DATA_LOADED = plant_capacity_data is not None and spv_capacity_data is not None
if not CAPACITY_DATA_LOADED:
    st.error("Essential capacity data from Excel could not be loaded. Please check file path and sheet names and reload.")
    # Optionally stop execution if this data is absolutely critical
    # st.stop()

# --- Sidebar ---
with st.sidebar:
    # Display Logo
    if os.path.exists(LOGO_PATH):
        try: logo_image = Image.open(LOGO_PATH); st.image(logo_image, width=150)
        except Exception as e: st.error(f"Logo Error: {e}")
    else: st.warning(f"Logo not found: {LOGO_PATH}")

    st.header("Filter Options")

    # Plant Selection
    if not available_plant_names: st.warning("No plant tables found."); selected_plants = []
    else: selected_plants = st.multiselect("Select Plant(s):", options=available_plant_names)

    # --- Dependent Filters (SPV, Year, Quarter) ---
    spv_options = []; year_options = []
    if selected_plants:
        # Use spinner when loading options based on plant selection
        with st.spinner("Loading filter options..."):
            options_data_subset = load_data(plant_names=selected_plants) # Load minimal data for filters
            if not options_data_subset.empty:
                if 'SPV' in options_data_subset.columns: spv_options = sorted(options_data_subset['SPV'].astype(str).unique())
                if 'Months' in options_data_subset.columns:
                    months_dt = pd.to_datetime(options_data_subset['Months'], errors='coerce')
                    year_options = sorted(months_dt.dt.year.dropna().unique().astype(int), reverse=True)

    # SPV Selection
    selected_spvs = st.multiselect("Select SPV(s):", options=spv_options, help="Leave blank to include all SPVs for selected Plant(s).")
    # Year Selection
    selected_years = st.multiselect("Select Year(s):", options=year_options, help="Leave blank to include all years.")
    # Quarter Selection
    quarter_options = ['All', 1, 2, 3, 4]
    selected_quarters = st.multiselect("Select Quarter(s):", options=quarter_options, default=['All'])

    st.caption("SPV & Year options update based on selected Plant(s).") # Explain dependency

# --- Main Dashboard Area ---
if not selected_plants:
    st.info("👈 Select one or more plants from the sidebar to view data.")
elif not CAPACITY_DATA_LOADED:
    # Error message shown during initial load
    st.info("Dashboard cannot be displayed as essential capacity information is missing.")
else:
    # Load the main dataset based on ALL active filters
    # Wrap this potentially longer operation in a spinner
    with st.spinner("Loading and filtering data..."):
        filtered_db_data = load_data(selected_plants, selected_spvs, selected_years, selected_quarters)

    if filtered_db_data.empty and selected_plants and (selected_spvs or selected_years or (selected_quarters != ['All'] and selected_quarters)):
         st.warning("No database records found matching all selected filters (Plant, SPV, Year, Quarter). Showing Plant-level info only.")
         # Allow proceeding to show plant gauges and potentially empty summary/SPV sections

    # --- Use TABS for selected plants ---
    if selected_plants:
        plant_tabs = st.tabs(selected_plants) # Create tabs with plant names

        for i, plant_name in enumerate(selected_plants):
            with plant_tabs[i]: # Work within the context of the current plant's tab
                st.subheader(f"Plant Overview: {plant_name}") # Header for the tab content

                # --- PLANT GAUGE Calculation (Uses Excel Data) ---
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
                with col_pg1: gauge_max_ac=max(1, plant_ac_capacity*1.2); fig_ac_p=go.Figure(go.Indicator(mode="gauge+number",value=plant_ac_capacity,title={'text':"AC Capacity(MW)"},gauge={'axis':{'range':[0,gauge_max_ac]},'bar':{'color':"darkorange"},'steps':[{'range':[0,gauge_max_ac],'color':"whitesmoke"}]})); fig_ac_p.update_layout(height=200, margin=dict(l=20,r=20,t=40,b=20)); st.plotly_chart(fig_ac_p, use_container_width=True,key=f"g_ac_p_{plant_name}")
                with col_pg2: gauge_max_dc=max(1, plant_dc_capacity*1.2); fig_dc_p=go.Figure(go.Indicator(mode="gauge+number",value=plant_dc_capacity,title={'text':"DC Capacity(MWp)"},gauge={'axis':{'range':[0,gauge_max_dc]},'bar':{'color':"mediumpurple"},'steps':[{'range':[0,gauge_max_dc],'color':"whitesmoke"}]})); fig_dc_p.update_layout(height=200, margin=dict(l=20,r=20,t=40,b=20)); st.plotly_chart(fig_dc_p, use_container_width=True,key=f"g_dc_p_{plant_name}")

                st.divider() # Visual separator

                # --- Plant Level Monthly Summary ---
                st.markdown("#### Plant Monthly Summary (Aggregated Across SPVs)")
                # Filter the MAIN filtered data for THIS plant
                plant_agg_data = filtered_db_data[filtered_db_data['Plant'] == plant_name].copy()
                if plant_agg_data.empty: st.caption(f"No DB data for Plant '{plant_name}' matching filters for summary.")
                elif 'Months' not in plant_agg_data.columns: st.warning(f"No 'Months' column for Plant '{plant_name}'.")
                else:
                    with st.spinner("Calculating plant summary..."): # Spinner for aggregation
                        plant_agg_data['Month_Year'] = plant_agg_data['Months'].dt.strftime('%b-%y')
                        plant_agg_data['Sort_Date'] = plant_agg_data['Months']
                        cols_to_sum = ["Budget Gen (MWHr)", "Actual Gen (MWHr)"] # MATCH EXACT NAMES
                        numeric_cols = plant_agg_data.select_dtypes(include='number').columns.tolist()
                        cols_to_exclude = ['AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Sort_Date']
                        cols_to_aggregate = [col for col in numeric_cols if col not in cols_to_exclude]
                        agg_dict = {'Sort_Date': 'min'}
                        for col in cols_to_aggregate: agg_dict[col] = 'sum' if col in cols_to_sum else 'mean'
                        if not any(c in agg_dict for c in cols_to_aggregate): st.caption(f"No data columns to summarize for Plant '{plant_name}'.")
                        else:
                            try:
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

                                # --- Add Download Button for Plant Summary ---
                                csv_summary = plant_summary[display_cols].to_csv(index=False).encode('utf-8')
                                st.download_button(
                                   label="Download Plant Summary as CSV",
                                   data=csv_summary,
                                   file_name=f'{plant_name}_monthly_summary.csv',
                                   mime='text/csv',
                                   key=f'download_summary_{plant_name}' # Unique key per plant tab
                                )
                                # --- End Download Button ---

                            except Exception as e: st.error(f"Error during plant summary aggregation: {e}")

                st.divider() # Visual separator

                # --- SPV Section for the current Plant ---
                st.markdown("#### SPV Details") # Header for SPV section
                plant_db_data_filtered_spv = filtered_db_data[filtered_db_data['Plant'] == plant_name]
                if 'SPV' not in plant_db_data_filtered_spv.columns:
                    if not plant_db_data_filtered_spv.empty: st.warning(f"No 'SPV' column found for Plant '{plant_name}'.")
                else:
                    spvs_in_filtered_data = plant_db_data_filtered_spv['SPV'].unique()
                    if not spvs_in_filtered_data.any():
                         if selected_spvs or selected_years or (selected_quarters != ['All'] and selected_quarters):
                             st.caption(f"No SPVs found for Plant '{plant_name}' matching the selected SPV/Year/Quarter filters.")
                         else: # No filters applied, but still no SPVs in the data for this plant
                             st.caption(f"No SPV data found for Plant '{plant_name}' in the database.")

                    # --- Loop through each relevant SPV and create an EXPANDER ---
                    for spv_name in spvs_in_filtered_data:
                        with st.expander(f"View Details for SPV: {spv_name}", expanded=False): # collapsed by default
                            # --- SPV GAUGE ---
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
                            with col_spv_g1: gauge_max_sac=max(1,spv_ac_cap*1.2); fig_ac_s=go.Figure(go.Indicator(mode="gauge+number",value=spv_ac_cap,title={'text':"AC Capacity(MW)"},gauge={'axis':{'range':[0,gauge_max_sac]},'bar':{'color':"#FF6347"},'steps':[{'range':[0,gauge_max_sac],'color':"whitesmoke"}]})); fig_ac_s.update_layout(height=200,margin=dict(l=10,r=10,t=40,b=10)); st.plotly_chart(fig_ac_s,use_container_width=True,key=f"g_ac_s_{plant_name}_{spv_name}") # Reduced height
                            with col_spv_g2: gauge_max_sdc=max(1,spv_dc_cap*1.2); fig_dc_s=go.Figure(go.Indicator(mode="gauge+number",value=spv_dc_cap,title={'text':"DC Capacity(MWp)"},gauge={'axis':{'range':[0,gauge_max_sdc]},'bar':{'color':"teal"},'steps':[{'range':[0,gauge_max_sdc],'color':"whitesmoke"}]})); fig_dc_s.update_layout(height=200,margin=dict(l=10,r=10,t=40,b=10)); st.plotly_chart(fig_dc_s,use_container_width=True,key=f"g_dc_s_{plant_name}_{spv_name}") # Reduced height

                            st.markdown("---") # Separator inside expander

                            # --- SPV Database Details Table ---
                            spv_db_data_filtered_for_table = plant_db_data_filtered_spv[plant_db_data_filtered_spv['SPV'] == spv_name]
                            if not spv_db_data_filtered_for_table.empty:
                                db_cols_to_exclude = ['SPV', 'Plant', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)', 'Months'] # Exclude original Months
                                available_columns = [c for c in spv_db_data_filtered_for_table.columns if c not in db_cols_to_exclude]
                                # Add formatted Month column for display
                                spv_db_data_filtered_for_table['Month'] = pd.to_datetime(spv_db_data_filtered_for_table['Months'], errors='coerce').dt.strftime('%b-%y')
                                if 'Month' not in available_columns: available_columns.insert(0, 'Month')

                                default_cols_count = min(len(available_columns), 6)
                                default_columns = available_columns[:default_cols_count]
                                st.markdown("**Monthly Database Details**")
                                selected_columns_display = st.multiselect(f"Select columns:", options=available_columns, default=default_columns, key=f"cols_{plant_name}_{spv_name}") # Simplified label

                                if selected_columns_display:
                                    df_to_style = spv_db_data_filtered_for_table[selected_columns_display].reset_index(drop=True)
                                    percent_cols_details = [c for c in selected_columns_display if '%' in c or c == 'Soil Loss (%)']
                                    formatters_details = get_formatters(df_to_style, percent_columns=percent_cols_details)
                                    if 'Month' in df_to_style.columns: formatters_details['Month'] = None # Don't format month column numerically
                                    styled_spv_details = df_to_style.style \
                                        .format(formatters_details, na_rep="N/A") \
                                        .set_properties(**{'text-align': 'right'}) \
                                        .set_properties(subset=['Month'], **{'text-align': 'left'}) # Align Month left

                                    st.dataframe(styled_spv_details, use_container_width=True, hide_index=True)

                                    # --- SPV Summary Section ---
                                    st.markdown("**Summary of Displayed Columns**")
                                    summary_data = {}
                                    selected_columns_calc = selected_columns_display # Use displayed columns directly now
                                    valid_selected_columns_calc = [c for c in selected_columns_calc if c in spv_db_data_filtered_for_table.columns and c != 'Month'] # Exclude Month
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
                                        elif valid_selected_columns_calc and all(summary_data.get(c)=="Non-numeric" or pd.isna(summary_data.get(c)) for c in valid_selected_columns_calc):
                                             st.caption("Selected columns have no numeric data.")

                                else: st.caption("No columns selected for display.")
                            else: st.caption(f"No monthly DB data available for SPV '{spv_name}'.")

# --- Footer ---
st.markdown("---")
now=datetime.datetime.now(); ct=now.strftime("%d-%b-%Y %H:%M:%S")
cf1, cf2 = st.columns([3, 1])
with cf1: st.markdown(f"<span style='font-size:12px;color:grey;'>© {now.year} Eden Renewables India LLP. All rights reserved.</span>", unsafe_allow_html=True)
with cf2: st.markdown(f"<span style='font-size:12px;color:grey;float:right;'>Last Refresh: {ct}</span>", unsafe_allow_html=True)
# --- End ---