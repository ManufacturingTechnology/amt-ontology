"""
compare_csv_diff.py
===================
Compare two CSV files and report rows that were added or removed.

The comparison is performed on a configurable set of key columns; all other
columns are ignored.  This makes the tool useful for auditing changes to
hierarchical category exports (Major / Sub / Product Category) without being
sensitive to unrelated column changes.

Usage
-----
    python compare_csv_diff.py <file1> <file2> [--keys COL [COL ...]]

Arguments
---------
file1       Path to the original (old) CSV.
file2       Path to the modified (new) CSV.
--keys      Space-separated list of column names to use as the composite key
            (default: "Major Category", "Sub Category", "Product Category").

Output
------
Prints added rows, removed rows, or a confirmation that the files are identical
with respect to the specified key columns.
"""

import argparse
import os

import pandas as pd

# Default key columns match the three-level category hierarchy used in exports
_DEFAULT_KEYS = ["Major Category", "Sub Category", "Product Category"]


def compare_csvs(file1: str, file2: str, key_columns: list[str]) -> None:
    """
    Compare two CSV files on *key_columns* and print a diff-style summary.

    Rows are compared by performing a full outer join on *key_columns*.
    Rows present only in *file2* are **added**; rows present only in *file1*
    are **removed**.

    Parameters
    ----------
    file1 : str
        Path to the original (old) CSV file.
    file2 : str
        Path to the modified (new) CSV file.
    key_columns : list[str]
        Column names to use as the composite row identity.
    """
    # keep_default_na=False ensures empty cells remain empty strings, not NaN
    df1 = pd.read_csv(file1, keep_default_na=False).fillna("")
    df2 = pd.read_csv(file2, keep_default_na=False).fillna("")

    comparison = pd.merge(df1, df2, on=key_columns, how="outer", indicator=True)

    added = comparison[comparison["_merge"] == "right_only"]
    removed = comparison[comparison["_merge"] == "left_only"]

    print("\n--- Comparison Results ---")
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

    if added.empty and removed.empty:
        print("\n[=] Files are identical with respect to the specified key columns.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare two CSV files and report added/removed rows."
    )
    parser.add_argument("file1", help="Path to the original/old CSV.")
    parser.add_argument("file2", help="Path to the modified/new CSV.")
    parser.add_argument(
        "--keys",
        nargs="+",
        default=_DEFAULT_KEYS,
        help=(
            "Columns to use as the composite row key for comparison "
            f"(default: {_DEFAULT_KEYS})."
        ),
    )
    args = parser.parse_args()

    if not os.path.exists(args.file1) or not os.path.exists(args.file2):
        print("Error: One or both input files do not exist.")
    else:
        compare_csvs(args.file1, args.file2, args.keys)