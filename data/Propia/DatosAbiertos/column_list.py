import csv
import glob
import os

output_file = 'headers.csv'

with open(output_file, 'w', newline='') as f_headers:
    csv_headers = csv.writer(f_headers)

    for csv_file in glob.glob('*.csv'):
        # Skip the output file so we don't try to read it as an input
        if csv_file == output_file:
            continue
            
        with open(csv_file, 'r', newline='') as f_csv:
            reader = csv.reader(f_csv)
            try:
                # Get the header and write it
                csv_headers.writerow([csv_file] + next(reader))
            except StopIteration:
                # This handles cases where other CSVs in the folder might be empty
                print(f"Skipping {csv_file}: File is empty.")

