# Guion final — Demo en vivo

**Proyecto Hybrid Cloud — REDATO**
**Equipo:** Alexia Aurrecochea · Valentín Rodríguez
**Duración estimada:** 12–15 minutos de demo

---

## Pre-vuelo (antes de empezar la defensa)

Hacer esto **una hora antes** de la defensa, no en vivo. Si algo falla acá, hay tiempo de arreglarlo.

### 1. Verificar Tailscale y levantar WireGuard

En tu WSL:

```bash
# Confirmar que Tailscale está conectado en ambos lados
tailscale status | head -3

# Levantar el túnel WireGuard
sudo wg-quick up wg0 2>/dev/null || true
sudo wg show
ping -c 3 10.100.0.2
```

Esperado: `latest handshake` reciente y 0% de pérdida en el ping.

Si el ping falla, coordiná con Valentín:
- Que corra `sudo wg-quick up wg0` en la Mac
- Verificar que las claves públicas coinciden en ambos lados

### 2. Restaurar el service mesh

```bash
cd ~/istio-1.22.0 && export PATH=$PATH:$HOME/istio-1.22.0/bin
~/startup-hybrid-cloud.sh
```

Esperado: ver el balanceo v1/v2 al final del script (ej. 6/4 o 7/3).

### 3. Levantar los exporters del observatorio

```bash
# Node Exporter (capas 1-2 y 4)
~/istio-1.22.0/node_exporter-1.8.1.linux-amd64/node_exporter 2>/dev/null &

# Blackbox Exporter con sudo (capa 3, ICMP raw)
sudo /home/alexi/istio-1.22.0/node_exporter-1.8.1.linux-amd64/blackbox_exporter-0.25.0.linux-amd64/blackbox_exporter \
  --config.file=/home/alexi/istio-1.22.0/node_exporter-1.8.1.linux-amd64/blackbox_exporter-0.25.0.linux-amd64/blackbox.yml \
  --log.level=error &

sleep 3

# Verificar
curl -s http://localhost:9100/metrics | grep -c "node_network_receive_bytes_total.*wg0"
curl -s "http://localhost:9115/probe?target=10.100.0.2&module=icmp" | grep "probe_success "
```

Esperado: `1` en el primer comando y `probe_success 1` en el segundo.

### 4. Aplicar workaround de Kiali multi-cluster

Kiali tiene un bug conocido con multi-cluster que rompe el grafo. Para la demo borramos el remote secret antes de abrir Kiali (esto no afecta el balanceo cross-cluster que ya está corriendo en memoria — solo evita que Kiali falle al cargar el grafo):

```bash
kubectl delete secret istio-remote-secret-cluster-b -n istio-system --context=cluster-a 2>/dev/null || true
kubectl rollout restart deployment/kiali -n istio-system --context=cluster-a
sleep 20
```

### 5. Abrir Grafana y Kiali en el navegador

```bash
# Grafana en una terminal
istioctl dashboard grafana --context=cluster-a &

# Kiali en otra
istioctl dashboard kiali --context=cluster-a &
```

En el navegador:
- **Grafana** → Dashboards → "Observatorio Multi-Capa OSI — Hybrid Cloud" → tiempo "Last 5 minutes" → refresh 5s
- **Kiali** → Traffic Graph → namespace `sample` → "Versioned app graph"

### 6. En la PC de Valentín (Mac)

```bash
# Servidor HTTP para la prueba del túnel
mkdir -p /tmp/demo
dd if=/dev/urandom of=/tmp/demo/testfile-10mb bs=1M count=10 2>/dev/null
python3 -m http.server 8888 --bind 10.100.0.2 --directory /tmp/demo &
```

---

## Acto 1 — Estado normal (4–5 minutos)

**Narrativa de apertura:** *"Vamos a mostrar la maqueta funcionando en condiciones normales. Primero el túnel, después generamos tráfico para ver el service mesh balanceando entre clusters en Kiali, después el observatorio multi-capa, y finalmente el pipeline de ML descargando datos desde Azure."*

### 1.1 Mostrar el túnel WireGuard

```bash
sudo wg show
ping -c 3 10.100.0.2
```

**Comentar:** *"Acá vemos el handshake reciente del túnel WireGuard. Estamos cifrando el tráfico con Curve25519 sobre el Noise Protocol. El RTT al cluster remoto es de ~95–160 ms — esto es Internet real, no una simulación de laboratorio."*

### 1.2 Generar tráfico sostenido para Kiali

En una terminal aparte, dejar tráfico continuo corriendo en background mientras se hace todo el resto del Acto 1:

```bash
# Tráfico continuo en background (mantener corriendo durante todo el Acto 1)
while true; do
  kubectl exec -n sample --context=cluster-a deploy/sleep -- curl -s helloworld:5000/hello > /dev/null
  sleep 0.3
done &
```

**Comentar:** *"Acabamos de lanzar tráfico continuo desde el cliente `sleep` hacia el servicio `helloworld`. Esto nos va a permitir ver el grafo en vivo en Kiali."*

### 1.3 Mostrar el balanceo cross-cluster en la terminal

```bash
# Sacar 10 peticiones rápidas para mostrar el balanceo v1/v2
for i in {1..10}; do
  kubectl exec -n sample --context=cluster-a deploy/sleep -- curl -s helloworld:5000/hello
done
```

**Comentar:** *"Cada petición la atiende una versión distinta del mismo servicio: v1 está en el cluster on-premise, v2 está en el cluster cloud en la Mac de Valentín. El cliente no sabe que están en redes distintas, máquinas distintas, sistemas operativos distintos. El service mesh balancea de forma transparente y todo el tráfico inter-servicio viaja con mTLS."*

### 1.4 Mostrar Kiali con el grafo en vivo

Cambiar a la pestaña de Kiali en el navegador. Apretar el botón de refrescar arriba a la derecha para ver el grafo actualizado.

**Qué señalar:**
- El nodo `sleep` enviando tráfico al servicio `helloworld`
- La flecha verde indicando que el tráfico fluye correctamente
- El nodo `v1` recibiendo las peticiones (el balanceo entre v1 y v2 ocurre, pero Kiali en este modo muestra el flujo dentro de cluster-a)
- El badge "A helloworld" debajo del nodo, indicando la app
- El tráfico activo del paso 1.2 manteniendo el grafo vivo

**Comentar:** *"En Kiali vemos el grafo del tráfico en tiempo real. El cliente `sleep` está enviando peticiones al servicio `helloworld`, y vemos la flecha verde indicando que el tráfico fluye con éxito. Todo el tráfico inter-servicio del mesh viaja con mTLS automáticamente —Istio se encarga de la autenticación y el cifrado entre los proxies Envoy sin que la aplicación tenga que hacer nada. Esto se logra con una CA compartida entre los dos clusters."*

**Importante:** Después de mostrar Kiali, dejarlo de lado. No vamos a volver — pasamos a Grafana para el resto de la demo. El tráfico en background del paso 1.2 se puede dejar corriendo, no molesta.

### 1.5 Mirar el observatorio multi-capa OSI

Cambiar a Grafana, dashboard del observatorio.

**Recorrer las capas:**
- *"Capa 1-2: RX/TX bytes en la interfaz wg0 — el tráfico que pasa por el túnel WireGuard."*
- *"Capa 3: RTT al cluster-b vía un probe ICMP de Blackbox Exporter. Conectividad = 1, todo verde."*
- *"Capa 4: conexiones TCP activas y retransmisiones — ahora en cero, todo limpio."*
- *"Capa 7: success rate del 100 %, latencia del helloworld. Las métricas vienen de Istio directamente."*

**Comentar:** *"Tenemos las cinco capas relevantes del modelo OSI en un solo dashboard, refrescando cada 5 segundos. Esto es la herramienta que vamos a usar para diagnosticar el problema en vivo en un momento."*

### 1.6 Lanzar el pipeline ML

```bash
cd ~/redato-hybrid-cloud
python3 pipeline/ml_pipeline.py
```

**Comentar mientras corre:** *"Este pipeline se conecta a Azure Blob Storage, descarga el dataset CIC-IDS2017 del Canadian Institute for Cybersecurity, lo preprocesa con pandas, y entrena un clasificador Random Forest para detectar tráfico anómalo. Los datos viven en la nube, el cómputo es on-premise, y la descarga atraviesa el túnel WireGuard. Esa es la esencia de Hybrid Cloud: orquestar datos y cómputo que viven en sitios distintos."*

**Resultados esperados:**
- 28.4 MB descargados en ~10 s a 2.6 MB/s
- 225 745 muestras, 128 027 DDoS + 97 718 BENIGN
- Accuracy 99.96 %

**Mientras corre, señalar Grafana:** *"Acá vemos en capa 1-2 los picos de RX bytes — esto es la descarga desde Azure pasando por el túnel."*

---

## Acto 2 — Diagnóstico de PMTU black hole en vivo (6–8 minutos)

**Narrativa:** *"Ahora vamos a inducir un problema clásico de redes sobre VPN y diagnosticarlo usando el observatorio que acabamos de mostrar."*

### 2.1 Explicar el problema antes de provocarlo

**Comentar:** *"El Path MTU Discovery, definido en el RFC 1191, es el mecanismo por el cual TCP descubre cuál es el paquete más grande que puede mandar sin fragmentarse. Funciona enviando paquetes con el bit DF —Don't Fragment— activado y esperando mensajes ICMP Fragmentation Needed, definidos en el RFC 792, si algún equipo intermedio no puede reenviarlos. El PMTU black hole, descripto en el RFC 2923, ocurre cuando esos mensajes ICMP son bloqueados por algún firewall en el camino: el emisor queda esperando ACKs que nunca llegan, sin error explícito. La conexión TCP se cuelga silenciosamente."*

### 2.2 Mostrar el mecanismo con ping

```bash
# Paquete que cabe en la MTU del túnel
ping -M do -s 1372 10.100.0.2 -c 3
```

**Esperado:** 0% de pérdida.

**Comentar:** *"Con el bit DF activado y 1372 bytes de payload, el paquete entra dentro de la MTU del túnel, que es 1420."*

```bash
# Paquete que supera la MTU
ping -M do -s 1400 10.100.0.2 -c 3
```

**Esperado:** `message too long, mtu=1420`, 100% pérdida.

**Comentar:** *"Al subir a 1400 bytes el sistema detecta el problema. En este caso el kernel local nos avisa, pero en un escenario real de black hole los ICMP son bloqueados por un router intermedio y la aplicación no recibe ningún error."*

### 2.3 Inducir el problema con observación en vivo

Tener Grafana visible en una ventana grande, dashboard refrescando cada 5 s, ventana de tiempo "Last 5 minutes".

En una terminal aparte, dejar el pipeline corriendo en loop para tener tráfico sostenido:

```bash
cd ~/redato-hybrid-cloud
while true; do python3 pipeline/ml_pipeline.py; sleep 5; done
```

**Comentar:** *"Dejamos el pipeline corriendo en loop para tener tráfico continuo sobre el túnel."*

Ahora inducir el black hole:

```bash
sudo ip link set wg0 mtu 576
sudo iptables -I OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP
sudo iptables -I FORWARD -p icmp --icmp-type fragmentation-needed -j DROP
echo "MTU reducida a 576 y ICMP bloqueado"
```

**Comentar mirando el dashboard:** *"Acabamos de bajar la MTU del túnel a 576 bytes y bloqueamos los mensajes ICMP de Fragmentation Needed. Esperemos 15–20 segundos y miremos qué pasa en el observatorio."*

**Qué señalar en el dashboard a medida que cambian las métricas:**
- **Capa 3 (RTT):** *"El RTT subió de ~1 ms a picos de 200–300 ms. La VPN sigue conectada pero el camino se degradó."*
- **Capa 4 (retransmisiones TCP):** *"Y acá está la evidencia clave del problema: las retransmisiones TCP, que antes estaban en cero, ahora aparecen en picos. El TCP está intentando reenviar paquetes que se pierden silenciosamente."*
- **Capa 1-2 (throughput):** *"El tráfico bruto sigue, pero con un patrón más entrecortado."*

### 2.4 Aplicar el fix con MSS clamping

```bash
# Restaurar MTU y limpiar ICMP
sudo ip link set wg0 mtu 1420
sudo iptables -D OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP
sudo iptables -D FORWARD -p icmp --icmp-type fragmentation-needed -j DROP

# Aplicar MSS clamping (la solución estándar para PMTU sobre VPN)
sudo iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
sudo iptables -t mangle -A OUTPUT -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

# Verificar
sudo iptables -t mangle -L | grep TCPMSS
```

**Comentar:** *"El MSS clamping intercepta el handshake TCP, los paquetes SYN y SYN-ACK, y ajusta el campo Maximum Segment Size para que nunca supere la MTU del túnel. Es la solución estándar en VPNs porque no depende de que los mensajes ICMP lleguen, y es transparente para la aplicación."*

### 2.5 Mostrar la recuperación en el dashboard

**Comentar, esperando 15 s y mirando Grafana:** *"En el siguiente intervalo de scrape, las retransmisiones de capa 4 vuelven a cero. El RTT se normaliza. El pipeline de ML sigue descargando sin perder bytes. La recuperación es inmediata, visible en el mismo dashboard que usamos para diagnosticar el problema."*

---

## Cierre (1–2 minutos)

**Comentar:** *"Lo que vimos en estos minutos: una arquitectura Hybrid Cloud completa con VPN WireGuard como enlace site-to-site entre dos PCs físicas con sistemas operativos distintos, un service mesh Istio con balanceo cross-cluster y mTLS automático, un pipeline real de Machine Learning consumiendo datos desde Azure on-demand, y un observatorio multi-capa OSI que nos permitió ver un problema clásico de redes simultáneamente en cuatro capas y aplicar la mitigación en vivo. Todas las capas relevantes para Hybrid Cloud, integradas en una sola maqueta funcional."*

---

## Limpieza post-demo

```bash
# Restaurar MTU y limpiar iptables
sudo ip link set wg0 mtu 1420
sudo iptables -D OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP 2>/dev/null || true
sudo iptables -D FORWARD -p icmp --icmp-type fragmentation-needed -j DROP 2>/dev/null || true
sudo iptables -t mangle -F

# Matar el loop del pipeline
kill %1 2>/dev/null || true
```

---

## Plan B — si algo falla en vivo

| Problema | Solución rápida |
|---|---|
| WireGuard sin handshake | `sudo wg-quick down wg0 && sudo wg-quick up wg0` |
| Kiali muestra "cluster not found" | `kubectl delete secret istio-remote-secret-cluster-b -n istio-system --context=cluster-a && kubectl rollout restart deployment/kiali -n istio-system --context=cluster-a` y esperar 20 s |
| Kiali muestra "No inbound traffic" | Verificar que el loop de tráfico del paso 1.2 sigue corriendo |
| El balanceo solo muestra v1 | Que Valentín corra `kubectl rollout restart deploy/helloworld-v2 -n sample --context=cluster-b` |
| Grafana no muestra datos | Verificar Prometheus: `curl localhost:9090/api/v1/targets` |
| Pipeline falla con timeout Azure | Re-ejecutarlo: probablemente fue un blip de red |
| Node/Blackbox Exporter no responde | Reiniciar el que falte (Blackbox necesita sudo) |

---

## Notas finales

- **Antes de mostrar Kiali**, lanzar el loop de tráfico en background (paso 1.2). Sin tráfico activo Kiali no muestra flechas.
- **Hablar mientras corre el pipeline**, no quedarse en silencio.
- **No leer los comandos** — explicarlos: *"esto baja la MTU"*, *"esto bloquea los ICMP"*.
- **Señalar el dashboard con el cursor** mientras se explica qué cambia y por qué.
- **Si una métrica tarda en aparecer**, decir *"esperamos al próximo scrape de Prometheus"* — está bien que se note que es un sistema real.
- **Kiali se va a romper cuando lanzamos el pipeline.** Por eso lo mostramos primero. No volver a Kiali en el resto de la demo.
