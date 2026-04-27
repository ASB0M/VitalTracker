import glob
import pandas as pd
import os

def compile_bidmc_data():
    # Define paths relative to the project root
    # Since this script runs from the project root or scripts folder, we'll use absolute-ish or robust relative paths.
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, 'data', 'raw', 'bidmc')
    
    print(f"Looking for CSV files in: {data_dir}")
    all_files = glob.glob(os.path.join(data_dir, '*_Numerics.csv'))
    
    if not all_files:
        print("No files found! Ensure the 53 _Numerics.csv files have been downloaded to data/raw/bidmc.")
        return

    dfs = []
    for f in all_files:
        try:
            # skipinitialspace=True removes the leading spaces in " HR" and " SpO2"
            temp = pd.read_csv(f, skipinitialspace=True)[['Time [s]', 'HR', 'SpO2']]
            
            # Rename 'Time [s]' to just 'Time' to match expected format
            temp.rename(columns={'Time [s]': 'Time'}, inplace=True)
            
            # Extract the patient ID safely
            patient_id = os.path.basename(f).split('bidmc')[-1].replace('_Numerics.csv', '').strip('_')
            temp['patient_id'] = patient_id
            
            dfs.append(temp)
        except Exception as e:
            print(f"Error processing {os.path.basename(f)}: {e}")

    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)
        output_file = os.path.join(data_dir, 'bidmc_compiled_numerics.csv')
        df_all.to_csv(output_file, index=False)
        print(f"Successfully compiled {len(df_all)} records.")
        print(f"Compiled dataset saved to: {output_file}")
    else:
        print("Failed to compile any dataframes.")

if __name__ == '__main__':
    compile_bidmc_data()
