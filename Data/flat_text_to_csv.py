import pandas as pd
import io

def process_text_to_flat_csv(input_file_path, output_file_path):
    # 1. Read the file
    # We use header=None because the file doesn't seem to have a header row.
    # We allow 'low_memory=False' to handle mixed data types if necessary.
    try:
        df = pd.read_csv(input_file_path, header=None, dtype=str, quotechar='"')
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 2. Identify Key Columns
    # Based on the file analysis:
    # Col 0: ID Number (Unique Identifier for the person)
    # Cols 6-9: Name components (Surname1, Surname2, Name1, Name2)
    # Col 13: Sanction Type (e.g., DESTITUCION)
    # Col 17: Authority Level (e.g., PRIMERA)
    # Col 18: Authority Name
    # Col 19: Date
    # Col 27: Duration/Details
    
    # We will assume Col 0 is the ID. We'll group by this ID.
    # We'll treat Cols 0-12 as "Static" person info (assuming they don't change much).
    # We'll treat Cols 13+ as "Event" info (Sanctions) that need to be pivoted.
    
    # Assign temporary generic column names
    df.columns = [f'Col_{i}' for i in range(df.shape[1])]
    
    # 3. Separate Static Info vs Variable Info
    # We take the first record of each person to get their basic details (Name, Job, etc.)
    # We group by the ID (Col_0)
    
    # Prepare a list to store processed records
    processed_rows = []
    
    grouped = df.groupby('Col_0')
    
    max_records = 0 # To track the max number of sanctions for column naming later
    
    for unique_id, group in grouped:
        # Take the static info from the first entry of the person
        # Columns 0 to 12 seem to be personal info (ID, Name, Job, Department, City)
        # We assume these don't change between records for the same ID.
        base_info = group.iloc[0, 0:13].to_dict()
        
        # Now flatten the variable info (Cols 13 to end) for ALL rows in this group
        variable_data = {}
        for idx, (_, row) in enumerate(group.iterrows()):
            # Get the variable columns (13 onwards)
            record_values = row[13:].to_dict()
            
            # Add them to the variable_data dict with a suffix index (e.g., _1, _2)
            for col_name, val in record_values.items():
                # Clean up the value (remove NaNs)
                val = "" if pd.isna(val) else str(val).strip()
                variable_data[f"{col_name}_{idx+1}"] = val
            
            if idx + 1 > max_records:
                max_records = idx + 1
                
        # Merge base info and variable info
        full_record = {**base_info, **variable_data}
        processed_rows.append(full_record)

    # 4. Create the final DataFrame
    flat_df = pd.DataFrame(processed_rows)
    
    # 5. Rename key columns for clarity (Optional, based on visual inspection)
    # You can adjust these names based on your specific knowledge of the data columns
    column_mapping = {
        'Col_0': 'ID_Number',
        'Col_1': 'Category',
        'Col_2': 'Role',
        'Col_6': 'Surname_1',
        'Col_7': 'Surname_2',
        'Col_8': 'Name_1',
        'Col_9': 'Name_2',
        'Col_10': 'Position',
        'Col_11': 'Department',
        'Col_12': 'City',
        # Variable columns will remain as Col_13_1, Col_13_2 etc.
        # Col_13 is usually "Sanction", Col_19 is "Date"
    }
    flat_df.rename(columns=column_mapping, inplace=True)

    # 6. Save to CSV
    flat_df.to_csv(output_file_path, index=False)
    print(f"Successfully created flattened CSV at: {output_file_path}")
    print(f"Total unique people processed: {len(flat_df)}")
    print(f"Max records per person found: {max_records}")

# --- Usage Example ---
# Replace 'your_input_file.txt' with the actual path to your downloaded text file
input_file = '/Users/simonb/Downloads/data_4f053991-40da-456e-9f71-a6ae406f715b_f3e390d2-7289-4642-b51c-84a3fb6964ea.txtt'
output_file = 'organized_people_data.csv'

# Only run this line if you have the file locally
process_text_to_flat_csv(input_file, output_file)
