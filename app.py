import streamlit as st
import pandas as pd
from openpyxl import load_workbook
from datetime import datetime
import time
import plotly.graph_objects as go
import os
import pyarrow.parquet as pq

# Streamlit app
st.set_page_config(page_title="Eden Renewables India LLP", page_icon="EDEN-Logo.png", layout="wide")
st.title("Eden Renewables India LLP")
st.write("This is an Actual dashboard for Eden Renewables India LLP, and we have currently displayed the BAP and UTT Plants and their SPV.")
st.write("Other Plant and their SPV will be available soon...")

# Sidebar logo
st.sidebar.image("EDEN-Logo.png", use_container_width=True)



# Sidebar theme selection
theme_option = st.sidebar.selectbox("Select Theme", options=["Light", "Dark", "Blue", "Green"])
if theme_option == "Dark":
    st.markdown(
        """
        <style>
        .reportview-container {
            background-color: #2B2B2B;
            color: white;
        }
        .stButton>button {
            background-color: #4CAF50; /* Green */
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
elif theme_option == "Blue":
    st.markdown(
        """
        <style>
        .reportview-container {
            background-color: #E0F7FA;
            color: black;
        }
        .stButton>button {
            background-color: #2196F3; /* Blue */
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
elif theme_option == "Green":
    st.markdown(
        """
        <style>
        .reportview-container {
            background-color: #E8F5E9;
            color: black;
        }
        .stButton>button {
            background-color: #4CAF50; /* Green */
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
        <style>
        .reportview-container {
            background-color: white;
            color: black;
        }
        .stButton>button {
            background-color: #f44336; /* Red */
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# Display Current Date and Time in the Sidebar
clock_placeholder = st.sidebar.empty()

# Function to update the digital clock display
def update_clock():
    while True:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clock_placeholder.write(f"**Current Date and Time:** {current_time}")
        time.sleep(10)  # Update every 10 seconds

# Specify the file, sheet, and table to read
sheet_name = "Dashboard_Data"
table_name = "Data"

@st.cache_data(ttl=3600)  # Refresh cache every hour
def read_excel_tables(file_path, sheet_name, table_name):
    try:
        wb = load_workbook(file_path, data_only=True)
        current_sheet = wb[sheet_name]

        if current_sheet.tables:
            for table in current_sheet.tables.values():
                if table.name == table_name:
                    data_range = table.ref
                    start_col, end_col = (
                        data_range.split(":")[0][0],
                        data_range.split(":")[1][0],
                    )
                    valid_data_range = f"{start_col}:{end_col}"  # Create a valid range for usecols
                    df = pd.read_excel(
                        file_path, sheet_name=sheet_name, header=0, usecols=valid_data_range
                    )
                    return df
        return None  # Return None if table not found
    except Exception as e:
        st.error(f"Error reading file {file_path}: {e}")
        return None

# Function to load and convert Excel to Parquet if needed, then read Parquet
@st.cache_data
def load_data():
    data_files = [f for f in os.listdir("data_files/") if f.endswith(".xlsx")]
    df_list = []

    for file in data_files:
        file_path = f"data_files/{file}"

        # Check if a Parquet file already exists
        parquet_file = file_path.replace(".xlsx", ".parquet")
        if os.path.exists(parquet_file):
            try:
                df = pd.read_parquet(parquet_file)
                df_list.append(df)  # Append the DF from parquet file
                continue  # skip to next file
            except Exception as e:
                st.error(f"Error reading Parquet file {parquet_file}: {e}")

        # Read excel and save as parquet
        df = read_excel_tables(file_path, sheet_name, table_name)  # Use the data reading function
        if df is not None:
            try:
                # **DATA TYPE CORRECTION BEFORE SAVING TO PARQUET**
                for col in df.columns:
                    if "Actual Grid Av(%)" in col:  # Use the *exact* column name.  Case sensitive!
                        # Remove '%' sign and convert to numeric, handling errors
                        df[col] = df[col].astype(str).str.replace('%', '', regex=False)
                        df[col] = pd.to_numeric(df[col], errors='coerce') / 100.0 #Convert to decimal representation

                    elif "Budget Gen\n(MWHr)" in col or "Actual Generation\n(MWHr)" in col or "Budgeted Generation\n(MWHr)" in col: #Target both potential column names.  Exact name needed.
                        # Convert to numeric, coerce errors to NaN, then fill with a safe default (0), and finally ensure it's float64
                         df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('float64')

                    elif "Soil Loss(%)" in col or "Soil loss(%)" in col:
                        #These columns should remain as strings. Don't try to convert them to numbers
                        df[col] = df[col].astype(str)

                df.to_parquet(parquet_file)
                df_list.append(df)
            except Exception as e:
                st.error(f"Error creating Parquet file {parquet_file}: {e} - {type(e)} - {e.__cause__}") #More information

    if df_list:
        df = pd.concat(df_list, ignore_index=True)
    else:
        df = pd.DataFrame()  # Empty DataFrame if no data is found
    return df  # Return the combined df

# Load data
df = load_data()

if not df.empty:
    # Convert 'Months' to datetime *once*
    df['Months'] = pd.to_datetime(df['Months'], errors='coerce')
    df['Plant'] = df['Plant'].astype('category')
    df['SPV'] = df['SPV'].astype('category')

    # Sidebar filters for Plant and SPV
    plant_options = df["Plant"].unique()

    # Use session state and a small delay to simulate debouncing
    if 'plant_selection' not in st.session_state:
        st.session_state.plant_selection = []

    selected_plants = st.sidebar.multiselect(
        "Select Plant", options=plant_options, key="plant_selection"
    )

    # Add a small delay
    time.sleep(0.1)

    # Filter the DataFrame based on selected Plant (EARLY FILTER)
    if selected_plants:
        filtered_df = df[df["Plant"].isin(selected_plants)].copy()
    else:
        filtered_df = df.copy()  # No filtering if no plants are selected

    # SPV filter options based on the selected Plants
    spv_options = filtered_df['SPV'].unique()

    if 'spv_selection' not in st.session_state:
        st.session_state.spv_selection = []

    selected_spvs = st.sidebar.multiselect(
        "Select SPV", options=spv_options, key="spv_selection"
    )

    # Add a small delay
    time.sleep(0.1)

    # Year Filter
    year_options = filtered_df["Months"].dt.year.unique()  # Use .dt.year directly

    if 'year_selection' not in st.session_state:
        st.session_state.year_selection = []

    selected_years = st.sidebar.multiselect(
        "Select Year", options=year_options, key="year_selection"
    )

    # Add a small delay
    time.sleep(0.1)

    # Filter the DataFrame based on selected Year
    if selected_years:
        filtered_df = filtered_df[filtered_df["Months"].dt.year.isin(selected_years)].copy()
    else:
        selected_years = []  # Reset if no data

    # Filter by SPV (if selected)
    if selected_spvs:
        filtered_df = filtered_df[filtered_df['SPV'].isin(selected_spvs)].copy()

    # Loop through each selected SPV and display corresponding data
    for spv in selected_spvs:  # Changed to selected_spvs, assuming you want to loop over SELECTED SPVs
        spv_filtered_df = filtered_df[filtered_df["SPV"] == spv].copy()

        # Display AC Capacity and Connected DC Capacity
        if not spv_filtered_df.empty:
            ac_capacity = spv_filtered_df["AC Capacity (MW)"].values[0]
            dc_capacity = spv_filtered_df["Connected DC Capacity (MWp)"].values[0]

            # Create two columns for the gauges
            col1, col2 = st.columns(2)  # Create two columns for the gauges
            with col1:
                ac_capacity_gauge = go.Figure(
                    go.Indicator(
                        mode="gauge+number",
                        value=ac_capacity,
                        title={"text": "AC Capacity (MW)"},
                        gauge={"axis": {"range": [0, max(ac_capacity, dc_capacity) * 1.1]}},
                        domain={"x": [0, 1], "y": [0, 1]},  # Adjust domain for width
                    )
                )
                st.plotly_chart(ac_capacity_gauge, key=f"ac_capacity_gauge_{spv}")  # Unique key

            with col2:
                dc_capacity_gauge = go.Figure(
                    go.Indicator(
                        mode="gauge+number",
                        value=dc_capacity,
                        title={"text": "Connected DC Capacity (MWp)"},
                        gauge={"axis": {"range": [0, max(ac_capacity, dc_capacity) * 1.1]}},
                        domain={"x": [0, 1], "y": [0, 1]},  # Adjust domain for width
                    )
                )
                st.plotly_chart(dc_capacity_gauge, key=f"dc_capacity_gauge_{spv}")  # Unique key

            # Move the "Table Data:" label below the gauges
            st.write(f"Table Data for SPV: {spv}")

            # Column selection excluding specified columns
            excluded_columns = ['Plant', 'SPV', 'AC Capacity (MW)', 'Connected DC Capacity (MWp)']
            available_columns = [col for col in spv_filtered_df.columns.tolist() if col not in excluded_columns]

            selected_columns = st.multiselect(
                "Select columns to display",
                available_columns,  # Use available_columns
                default=available_columns[:min(5, len(available_columns))],  # limit default selection
                key=f"column_selection_{spv}",
            )

            # Format the DataFrame
            formatted_df = spv_filtered_df[selected_columns].copy()
            # Replace NaN values with 0
            formatted_df.fillna(0, inplace=True)  # Replace NaN values with 0
            formatted_df = formatted_df.infer_objects()  # Ensure correct data types

            # Apply formatting
            for col in formatted_df.columns:
                if col == "Months":
                    formatted_df[col] = formatted_df[col].dt.strftime('%b-%y')

                elif "%" in col:
                    # Convert to numeric first
                    formatted_df[col] = pd.to_numeric(formatted_df[col], errors='coerce').fillna(0)
                    formatted_df[col] = formatted_df[col].map(lambda x: f"{x:.2f}%")

                else:
                    # Convert to numeric first
                    formatted_df[col] = pd.to_numeric(formatted_df[col], errors='coerce').fillna(0)
                    formatted_df[col] = formatted_df[col].map(lambda x: f"{x:.2f}")

            # Display the formatted DataFrame in Streamlit with center alignment
            st.dataframe(
                formatted_df.style.set_properties(**{"text-align": "center"}),
                use_container_width=True,
                hide_index=True,
            )

else:
    st.write("No data found for the specified table.")

# Update the live clock every 10 seconds
update_clock()
