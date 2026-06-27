# Redato: Hybrid Cloud

Implementación de una arquitectura **Hybrid Cloud** que conecta un clúster *on-prem* con un clúster en la nube a través de una **VPN site-to-site WireGuard**, sobre la que se despliega un **service mesh Istio multi-primario** (multi-cluster / multi-network). El proyecto integra un pipeline de Machine Learning para detección de tráfico anómalo, una batería de experimentos de performance con k6 y una demostración de diagnóstico de red por capas (PMTU black hole).

Proyecto del curso **Redes de Datos**, Universidad Católica del Uruguay.

---

## Arquitectura

```
        Cluster A (on-prem)                         Cluster B (cloud)
   ┌────────────────────────┐                  ┌────────────────────────┐
   │  k3d / Istio            │                  │  k3d / Istio            │
   │  meshID: mesh1          │   east-west GW   │  meshID: mesh1          │
   │  cluster: cluster-a     │ ←──────────────→ │  cluster: cluster-b     │
   │  network: network1      │   (mTLS)         │  network: network2      │
   └───────────┬────────────┘                  └───────────┬────────────┘
               │                                            │
               └──────────── túnel WireGuard ───────────────┘
                       (over Tailscale, MTU 1420)
```

- **Conectividad:** túnel WireGuard sobre Tailscale entre ambos sitios.
- **Service mesh:** Istio en topología *multi-primary multi-network*, con *east-west gateway* para el descubrimiento de servicios entre clústeres y **mTLS** activo en el tráfico interno.
- **Observabilidad:** stack Kiali + Prometheus + Grafana + Jaeger.
- **Caso de uso:** pipeline de ML que consume datos desde Azure Blob Storage a través del túnel y entrena un clasificador de tráfico anómalo.

---

## Estructura del repositorio

```
redato-hybrid-cloud/
├── mesh/                       # Service mesh Istio
│   ├── istio-a.yaml            # IstioOperator — cluster-a (mesh1 / network1)
│   ├── istio-b.yaml            # IstioOperator — cluster-b (mesh1 / network2)
│   ├── README-mesh.md
│   └── policies/               # Políticas de tráfico
│       ├── canary.yaml         # Canary release (VirtualService 90/10 + DestinationRule)
│       ├── circuit-breaker.yaml
│       └── retries.yaml
│
├── pipeline/                   # Pipeline de ML
│   ├── csv_to_parquet.py       # Conversión CIC-IDS2017 CSV → Parquet (snappy)
│   └── ml_pipeline.py          # Descarga desde Azure Blob + Random Forest
│
├── experiments/                # Pruebas de performance (k6)
│   ├── load-test.js            # Test de carga k6 (constant-arrival-rate, 10 req/s, 2m)
│   ├── analyze.py              # Parseo de resultados k6 + stats + gráfica
│   ├── run-all.sh              # Orquestación de las corridas
│   └── results/
│       ├── baseline-mesh-run1.json
│       ├── wan-degraded-mesh-run1.json
│       ├── no-mesh-run1.json
│       ├── summary.csv         # Media / mediana / p95 / desvío por escenario
│       └── latencia-comparacion.png
│
├── capturas/                   # Capturas para el informe
│   ├── kiali1.png  kiali2.png            # Grafo de tráfico con mTLS
│   ├── graphana1.png … graphana3.png     # Istio Service Dashboard
│   └── graphanaMultiCapa.png             # Observatorio Multi-Capa OSI
│
├── demo/                       # Capturas del Observatorio Multi-Capa (demo en vivo)
│   └── graphanamulti1.png … graphanamulti5.png
│
└── PMTU.md                     # Guion de la demo: PMTU black hole y MSS clamping
```

---

## Componentes

### Service mesh (Istio)

Topología *multi-primary*: ambos clústeres comparten `meshID: mesh1` pero pertenecen a redes distintas (`network1` / `network2`), conectadas por un *east-west gateway*. Esto permite que un servicio en el clúster A descubra e invoque servicios del clúster B con mTLS de extremo a extremo.

Las políticas de tráfico en `mesh/policies/` demuestran capacidades de resiliencia y *progressive delivery* del mesh:

- **Canary release** — reparto de tráfico 90/10 entre `v1` y `v2` del servicio `helloworld`.
- **Circuit breaker** — corte de tráfico ante fallos sostenidos.
- **Retries** — reintentos automáticos a nivel de mesh.

### Pipeline de ML

Detección de tráfico anómalo sobre el dataset **CIC-IDS2017** (Canadian Institute for Cybersecurity):

1. `csv_to_parquet.py` convierte los CSV originales a Parquet con compresión snappy, limpiando valores infinitos y normalizando nombres de columnas.
2. `ml_pipeline.py` descarga los datos desde **Azure Blob Storage a través del túnel WireGuard**, entrena un `RandomForestClassifier` (scikit-learn) y reporta accuracy y métricas por clase.

### Experimentos de performance (k6)

`load-test.js` ejecuta una carga constante (`constant-arrival-rate`, 10 req/s durante 2 min) contra el servicio detrás del mesh. Se evalúan tres escenarios:

| Escenario | Media (ms) | Mediana (ms) | p95 (ms) | Desvío (ms) |
|---|---|---|---|---|
| Con mesh (baseline) | 54.82 | 53.96 | 63.02 | 5.12 |
| Con mesh (WAN degradada) | 52.62 | 51.63 | 59.29 | 4.65 |
| Sin mesh (100% error) | 0.01 | 0.00 | 0.00 | 0.32 |

> El escenario "sin mesh" registra latencias cercanas a cero porque las peticiones fallan inmediatamente (sin ruta de servicio), evidenciando el rol del mesh en el descubrimiento y enrutamiento entre clústeres.

`analyze.py` parsea las salidas JSON de k6, calcula las estadísticas (`summary.csv`) y genera la gráfica comparativa (`latencia-comparacion.png`).

### Diagnóstico de red — PMTU black hole

`PMTU.md` documenta el guion de la demostración del problema de *Path MTU Discovery* sobre el túnel WireGuard y su resolución mediante **MSS clamping** en iptables, con análisis por capas OSI y referencia a los RFC relevantes (791, 792, 1191, 2923, 4821).

---

## Cómo reproducir

> Requisitos: `k3d`, `istioctl`, `kubectl`, WireGuard/Tailscale, `k6`, Python 3.10+.

```bash
# 1. Levantar los clústeres e instalar Istio en cada uno
istioctl install -f mesh/istio-a.yaml   # sobre el contexto de cluster-a
istioctl install -f mesh/istio-b.yaml   # sobre el contexto de cluster-b

# 2. Aplicar políticas de tráfico
kubectl apply -f mesh/policies/

# 3. Pipeline de ML
pip install pandas scikit-learn pyarrow azure-storage-blob
python pipeline/csv_to_parquet.py        # CSV → Parquet
python pipeline/ml_pipeline.py           # descarga desde Azure + entrenamiento

# 4. Experimentos de carga
TARGET=http://<servicio>:8080 k6 run experiments/load-test.js
python experiments/analyze.py            # genera summary.csv y la gráfica
```

---

## Nota de seguridad

`pipeline/ml_pipeline.py` contenía un **SAS token de Azure embebido en el código**. Las credenciales no deben versionarse en un repositorio público. Antes de reutilizar el pipeline:

1. Revocar/regenerar el SAS token desde el portal de Azure.
2. Mover la credencial a una variable de entorno (p. ej. `os.environ["AZURE_SAS_TOKEN"]`) o a un archivo `.env` ignorado por Git.

---

## Equipo

Proyecto desarrollado en equipo por Alexia Aurrecochea, Valentín Rodriguez,  Martina Caetano y Mikaela Maldonado.

Curso REDATO — Universidad Católica del Uruguay.
