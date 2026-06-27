"""
Pipeline de ML para detección de tráfico anómalo — REDATO Hybrid Cloud
Consume datos desde Azure Blob Storage a través del túnel WireGuard (VPN site-to-site)
Dataset: CIC-IDS2017 (Canadian Institute for Cybersecurity)
"""

import time
import pandas as pd
from azure.storage.blob import BlobServiceClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings('ignore')

# Configuración Azure
ACCOUNT = "redatoequipo1aurrecochea"
CONTAINER = "cic-ids2017"
SAS_TOKEN = "se=2026-07-26T16%3A53Z&sp=rl&sv=2026-04-06&sr=c&sig=aYSBDUq9S%2BrUlj6IOA5ePkEdHlpeTuAPfxlQQIsgNoU%3D"
BLOB_NAME = "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.parquet"

def download_from_azure():
    print(f"[1/4] Conectando a Azure Blob Storage...")
    print(f"      Account: {ACCOUNT}")
    print(f"      Container: {CONTAINER}")
    print(f"      Blob: {BLOB_NAME}")
    
    url = f"https://{ACCOUNT}.blob.core.windows.net"
    client = BlobServiceClient(account_url=url, credential=SAS_TOKEN)
    container_client = client.get_container_client(CONTAINER)
    blob_client = container_client.get_blob_client(BLOB_NAME)
    
    start = time.time()
    print(f"      Descargando datos a través del túnel WireGuard...")
    data = blob_client.download_blob().readall()
    elapsed = time.time() - start
    
    size_mb = len(data) / (1024 * 1024)
    throughput = size_mb / elapsed
    print(f"      ✓ {size_mb:.1f} MB descargados en {elapsed:.1f}s ({throughput:.1f} MB/s)")
    return data

def preprocess(data):
    print(f"\n[2/4] Preprocesando datos...")
    import io
    df = pd.read_parquet(io.BytesIO(data))
    print(f"      Shape original: {df.shape}")
    print(f"      Clases: {df['Label'].value_counts().to_dict()}")
    
    # Limpiar
    df = df.replace([float('inf'), float('-inf')], float('nan')).dropna()
    
    # Features numéricas
    feature_cols = [c for c in df.columns if c != 'Label' and df[c].dtype in ['float64', 'int64']][:20]
    X = df[feature_cols]
    
    # Encode labels
    le = LabelEncoder()
    y = le.fit_transform(df['Label'])
    
    print(f"      ✓ {len(df)} muestras, {len(feature_cols)} features")
    print(f"      Clases codificadas: {dict(zip(le.classes_, range(len(le.classes_))))}")
    return X, y, le

def train(X, y):
    print(f"\n[3/4] Entrenando clasificador Random Forest...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    start = time.time()
    clf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)
    elapsed = time.time() - start
    
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"      ✓ Entrenado en {elapsed:.1f}s")
    print(f"      Accuracy: {acc:.4f} ({acc*100:.2f}%)")
    return clf, X_test, y_test, y_pred

def report(clf, X_test, y_test, y_pred, le):
    print(f"\n[4/4] Reporte de clasificación:")
    print("-" * 50)
    print(classification_report(y_test, y_pred, target_names=le.classes_))

if __name__ == "__main__":
    print("=" * 60)
    print("  Pipeline ML — Detección de Tráfico Anómalo")
    print("  Hybrid Cloud: Azure Blob Storage → on-prem via WireGuard")
    print("=" * 60)
    
    data = download_from_azure()
    X, y, le = preprocess(data)
    clf, X_test, y_test, y_pred = train(X, y)
    report(clf, X_test, y_test, y_pred, le)
    
    print("\n✓ Pipeline completado exitosamente")
