import pandas as pd
import argparse
import os

def compare_csvs(file1, file2, key_columns):
    # Load files, ensuring empty cells are empty strings
    df1 = pd.read_csv(file1, keep_default_na=False).fillna("")
    df2 = pd.read_csv(file2, keep_default_na=False).fillna("")

    # 1. Find Added Rows (In File 2 but not in File 1)
    # We do an outer join and look for 'right_only'
    comparison = pd.merge(df1, df2, on=key_columns, how='outer', indicator=True)
    
    added = comparison[comparison['_merge'] == 'right_only']
    removed = comparison[comparison['_merge'] == 'left_only']
    
    print(f"\n--- Comparison Results ---")
    print(f"File 1 (Old): {file1}")
    print(f"File 2 (New): {file2}")
    print("-" * 30)

    if not added.empty:
        print(f"\n[+] ADDED ROWS ({len(added)}):")
        print(added[key_columns].to_string(index=False))
    else:
        print("\n[ ] No new rows added.")

    if not removed.empty:
        print(f"\n[-] REMOVED ROWS ({len(removed)}):")
        print(removed[key_columns].to_string(index=False))
    else:
        print("\n[ ] No rows removed.")

    # 2. Check for "Exact Match"
    if added.empty and removed.empty:
        print("\n[!] Files are identical in terms of the specified key columns.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare two CSV files.")
    parser.add_argument("file1", help="Path to the original/old CSV.")
    parser.add_argument("file2", help="Path to the modified/new CSV.")
    # Defaulting to your hierarchy columns
    parser.add_argument("--keys", nargs="+", default=["Major Category", "Sub Category", "Product Category"], 
                        help="Columns to use as the unique key for comparison.")
    
    args = parser.parse_args()

    if os.path.exists(args.file1) and os.path.exists(args.file2):
        compare_csvs(args.file1, args.file2, args.keys)
    else:
        print("Error: One or both files do not exist.")