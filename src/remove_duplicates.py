import csv
import os

def remove_duplicates(csv_files_list, target_csv_file, output_file=None):
    """
    Remove duplicate rows from target_csv_file that appear in any of the csv_files_list
    
    Args:
        csv_files_list: List of CSV file paths to check for duplicates
        target_csv_file: CSV file to remove duplicates from
        output_file: Optional output file path (defaults to overwriting target_csv_file)
    """
    # Read all rows from the CSV files list into a set for fast lookup
    existing_rows = set()
    
    for csv_file in csv_files_list:
        if os.path.exists(csv_file):
            with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    existing_rows.add(tuple(row))
    
    # Read target CSV and keep only unique rows
    unique_rows = []
    header = None
    
    with open(target_csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)  # Save header
        
        for row in reader:
            if tuple(row) not in existing_rows:
                unique_rows.append(row)
    
    # Write deduplicated data
    output_path = output_file if output_file else target_csv_file
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(header)
        writer.writerows(unique_rows)
    
    print(f"Removed {len(existing_rows)} duplicate rows. Saved {len(unique_rows)} unique rows to: {output_path}")

if __name__=='__main__':
    # # Remove duplicates and save to new file
    # remove_duplicates(['file1.csv', 'file2.csv'], 'target.csv', 'clean_output.csv')

    # Remove duplicates and overwrite target file
    remove_duplicates(['/home/geshuhang/aws_image_download/urls/cover_urls_20250822_010628.csv'], '/home/geshuhang/aws_image_download/urls/cover_urls_20250823_035447.csv')