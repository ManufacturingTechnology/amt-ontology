import csv

def diff_rows_by_columns(csv_a, csv_b, cols=("Major Category", "Sub Category", "Product Category")):
    def load_set(path):
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for c in cols:
                if c not in reader.fieldnames:
                    raise ValueError(f"Column '{c}' not found in {path}")
            values = set()
            for row in reader:
                parts = [(row[c] or "").strip() for c in cols]
                key = " ".join(parts).strip()   # "<col1> <col2> <col3>"
                if key:
                    values.add(key)
        return values

    a = load_set(csv_a)
    b = load_set(csv_b)

    only_in_a = sorted(a - b)
    only_in_b = sorted(b - a)

    return only_in_a, only_in_b

if __name__ == "__main__":
    file1 = "resources/IMTS Exhibitor Categories.csv" #Generated from OWL model
    file2 = "resources/imts_exhibitor_categories.csv" #Generated from JSON model
    only_in_1, only_in_2 = diff_rows_by_columns(file1, file2)

    if only_in_1 or only_in_2:
        print("In OWL output but not in JSON output:")
        for v in only_in_1:
            print("  ", v)

        print("\nIn JSON output but not OWL output:")
        for v in only_in_2:
            print("  ", v)

        raise Exception
    
    else:
        print("JSON and OWL outputs are the same.")
