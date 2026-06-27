import json
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

def parse_k6_json(filepath):
    rows = []
    scenario = filepath.split('/')[-1].replace('.json', '')
    with open(filepath) as f:
        for line in f:
            try:
                d = json.loads(line)
                if d.get('type') == 'Point' and d.get('metric') == 'http_req_duration':
                    rows.append({
                        'scenario': scenario,
                        'duration_ms': d['data']['value']
                    })
            except:
                pass
    return rows

files = glob.glob('experiments/results/*.json')
all_rows = []
for f in files:
    all_rows.extend(parse_k6_json(f))

df = pd.DataFrame(all_rows)

# Renombrar escenarios para que sean más claros
rename = {
    'baseline-mesh-run1': 'Con mesh\n(baseline)',
    'wan-degraded-mesh-run1': 'Con mesh\n(WAN degradada)',
    'no-mesh-run1': 'Sin mesh\n(100% error)'
}
df['scenario'] = df['scenario'].map(rename)
df = df.dropna()

# Stats
print("\n=== Resumen estadístico ===")
summary = df.groupby('scenario')['duration_ms'].agg(['mean', 'median', 
    lambda x: x.quantile(0.95), 'std'])
summary.columns = ['Media (ms)', 'Mediana (ms)', 'p95 (ms)', 'Desvío (ms)']
print(summary.round(2))
summary.round(2).to_csv('experiments/results/summary.csv')

# Gráfico
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Boxplot
df.boxplot(column='duration_ms', by='scenario', ax=axes[0])
axes[0].set_title('Distribución de latencia por escenario')
axes[0].set_xlabel('Escenario')
axes[0].set_ylabel('Latencia (ms)')
plt.sca(axes[0])
plt.xticks(rotation=15, ha='right')

# Barras p95
scenarios = summary.index.tolist()
p95_values = summary['p95 (ms)'].tolist()
colors = ['#2196F3', '#4CAF50', '#F44336']
axes[1].bar(range(len(scenarios)), p95_values, color=colors)
axes[1].set_xticks(range(len(scenarios)))
axes[1].set_xticklabels(scenarios, rotation=15, ha='right')
axes[1].set_title('Latencia p95 por escenario')
axes[1].set_ylabel('Latencia p95 (ms)')
for i, v in enumerate(p95_values):
    axes[1].text(i, v + 0.5, f'{v:.1f}ms', ha='center', fontsize=10)

plt.suptitle('Análisis de performance: Service Mesh Hybrid Cloud', fontsize=13)
plt.tight_layout()
plt.savefig('experiments/results/latencia-comparacion.png', dpi=150, bbox_inches='tight')
print("\nGráfica guardada en experiments/results/latencia-comparacion.png")
