import pandas as pd
import os

file_path = 'scripts/新高考数学目录.xlsx'
if not os.path.exists(file_path):
    print(f"File not found: {file_path}")
    exit(1)

df = pd.read_excel(file_path)
print("Columns:", df.columns.tolist())
print("First 5 rows:")
print(df.head().to_string())
