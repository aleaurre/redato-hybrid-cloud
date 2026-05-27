import pandas as pd
import os, glob

# Ruta a la carpeta del proyecto (sube un nivel desde pipeline/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INPUT_DIR = os.path.join(PROJECT_ROOT, "cic-ids2017")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "cic-ids2017-parquet")
os.makedirs(OUTPUT_DIR, exist_ok=True)

csv_files = glob.glob(f"{INPUT_DIR}/*.csv")
print(f"Encontrados {len(csv_files)} CSVs en {INPUT_DIR}")

for csv_file in csv_files:
    print(f"Procesando {csv_file}...")
    df = pd.read_csv(csv_file, low_memory=False, encoding='latin-1')
    df.columns = [c.strip() for c in df.columns]
    numeric_cols = df.select_dtypes(include='number').columns
    df[numeric_cols] = df[numeric_cols].replace(
        [float('inf'), float('-inf')], float('nan')
    )
    base = os.path.basename(csv_file).replace('.csv', '.parquet')
    output_path = os.path.join(OUTPUT_DIR, base)
    df.to_parquet(output_path, compression='snappy', index=False)
    
    size_csv = os.path.getsize(csv_file) / 1024 / 1024
    size_parquet = os.path.getsize(output_path) / 1024 / 1024
    print(f"  → {base} ({size_csv:.1f} MB → {size_parquet:.1f} MB)")

print(f"\nListo. Parquets en: {OUTPUT_DIR}")