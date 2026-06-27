# Guion final — Demo en vivo

**Proyecto Hybrid Cloud — REDATO**
**Equipo:** Alexia Aurrecochea · Valentín Rodríguez
**Duración estimada:** 12–15 minutos de demo (dentro de la presentación de 30)

---

## Pre-vuelo (antes de empezar la defensa)

Hacer esto **una hora antes** de la defensa, no en vivo. Si algo falla acá, hay tiempo de arreglarlo.

### En la PC de Ale (WSL Ubuntu, cluster-a)

```bash
# Verificar que Tailscale está conectado
tailscale status | head -3

# Verificar WireGuard
sudo wg show
ping -c 2 10.100.0.2
```

```bash
# Restaurar el mesh y validar balanceo cross-cluster
cd ~/istio-1.22.0 && export PATH=$PATH:$HOME/istio-1.22.0/bin
~/startup-hybrid-cloud.sh
```

```bash
# Confirmar que balancea v1 + v2
for i in {1..10}; do
  kubectl exec -n sample --context=cluster-a deploy/sleep -- curl -s helloworld:5000/hello
done | sort | uniq -c
```

Salida esperada: una mezcla de v1 y v2 (ej. 7/3 o 6/4). Si todo es v1, hay que reiniciar helloworld-v2 desde la Mac.

```bash
# Levantar Node Exporter (capa 1-2 y 4)
~/istio-1.22.0/node_exporter-1.8.1.linux-amd64/node_exporter 2>/dev/null &

# Levantar Blackbox Exporter con sudo (capa 3, necesita ICMP raw)
sudo /home/alexi/istio-1.22.0/node_exporter-1.8.1.linux-amd64/blackbox_exporter-0.25.0.linux-amd64/blackbox_exporter \
  --config.file=/home/alexi/istio-1.22.0/node_exporter-1.8.1.linux-amd64/blackbox_exporter-0.25.0.linux-amd64/blackbox.yml \
  --log.level=error &
```

```bash
# Verificar que ambos exporters responden
curl -s http://localhost:9100/metrics | grep -c "node_network_receive_bytes_total.*wg0"
curl -s "http://localhost:9115/probe?target=10.100.0.2&module=icmp" | grep "probe_success "
```

Esperado: `1` en el primer comando y `probe_success 1` en el segundo.

```bash
# Abrir Grafana
istioctl dashboard grafana --context=cluster-a &

# Abrir Kiali (en otra terminal)
istioctl dashboard kiali --context=cluster-a &
```

En el navegador:
- Grafana → Dashboards → "Observatorio Multi-Capa OSI — Hybrid Cloud" → tiempo "Last 5 minutes" → refresh 5s
- Kiali → Traffic Graph → namespace sample → "Versioned app graph"

### En la PC de Valentín (Mac, cluster-b)

```bash
# Levantar servidor HTTP para la prueba del túnel
mkdir -p /tmp/demo
dd if=/dev/urandom of=/tmp/demo/testfile-10mb bs=1M count=10 2>/dev/null
python3 -m http.server 8888 --bind 10.100.0.2 --directory /tmp/demo &
```

---

## Acto 1 — Estado normal (3–4 minutos)

**Narrativa:** *"Empezamos mostrando el sistema completo funcionando en condiciones normales."*

### 1.1 Mostrar el túnel WireGuard

```bash
# Mostrar el estado del túnel
sudo wg show

# Demostrar que la VPN cifrada funciona
ping -c 3 10.100.0.2
```

**Comentario:** *"Acá vemos el handshake reciente del túnel y la conectividad punto a punto. El RTT de ~25–30 ms es normal sobre Internet."*

### 1.2 Mostrar el balanceo cross-cluster del service mesh

```bash
for i in {1..10}; do
  kubectl exec -n sample --context=cluster-a deploy/sleep -- curl -s helloworld:5000/hello
done
```

**Comentario:** *"Cada petición la atiende una versión distinta: v1 está en el cluster on-prem, v2 está en el cluster cloud en la Mac de Valentín. El mesh balancea sin que el cliente sepa que están en redes distintas."*

### 1.3 Mostrar Kiali

Cambiar a la pestaña de Kiali en el navegador.

**Comentario:** *"En Kiali vemos el grafo del tráfico en tiempo real. La flecha verde de sleep a helloworld indica 100 % de success rate. El candado en el enlace indica que el tráfico viaja con mTLS — todo el tráfico inter-servicio del mesh está cifrado automáticamente."*

### 1.4 Lanzar el pipeline ML

```bash
cd ~/redato-hybrid-cloud
python3 pipeline/ml_pipeline.py
```

**Comentario mientras corre:** *"Este pipeline descarga el dataset CIC-IDS2017 desde Azure Blob Storage a través del túnel WireGuard, lo preprocesa y entrena un clasificador Random Forest para detección de tráfico anómalo. Los datos viven en la nube, el cómputo es on-premise — eso es Hybrid Cloud."*

**Resultados esperados:**
- 28.4 MB descargados en ~10s a 2.6 MB/s
- 225 745 muestras, 128 027 DDoS + 97 718 BENIGN
- Accuracy 99.96 %

### 1.5 Mostrar el observatorio en estado nominal

Cambiar a Grafana, dashboard del observatorio multi-capa.

**Comentario, recorriendo las capas:**
- *"Capa 1-2: vemos los picos de RX/TX bytes en wg0 — eso es la descarga desde Azure pasando por el túnel."*
- *"Capa 3: el RTT al cluster-b se mantiene en ~1 ms vía el probe ICMP de Blackbox Exporter, conectividad = 1."*
- *"Capa 4: conexiones TCP activas estables, retransmisiones en cero."*
- *"Capa 7: success rate 100 %, latencia del helloworld estable. Las métricas vienen de Istio."*

---

## Acto 2 — Diagnóstico de PMTU black hole en vivo (6–8 minutos)

**Narrativa:** *"Ahora vamos a inducir un problema clásico de redes en VPN y diagnosticarlo usando el observatorio."*

### 2.1 Explicar el problema antes de provocarlo

**Comentario:** *"El Path MTU Discovery, definido en el RFC 1191, es el mecanismo por el cual TCP descubre cuál es el paquete más grande que puede mandar sin fragmentarse. Funciona enviando paquetes con el bit DF activado y esperando mensajes ICMP Fragmentation Needed —definidos en el RFC 792— si algún equipo en el camino no puede reenviarlos. El PMTU black hole ocurre cuando esos ICMP son bloqueados: el emisor queda esperando ACKs que nunca llegan, sin error explícito. La conexión se cuelga silenciosamente."*

### 2.2 Mostrar el mecanismo PMTU con ping

```bash
# Paquete que cabe en la MTU del túnel (1420 bytes)
ping -M do -s 1372 10.100.0.2 -c 3
```

**Esperado:** 0 % de pérdida, RTT ~25–30 ms.

**Comentario:** *"Con el bit DF activado y 1372 bytes de payload —1400 bytes con headers IP— el paquete entra dentro de la MTU del túnel."*

```bash
# Paquete que supera la MTU
ping -M do -s 1400 10.100.0.2 -c 3
```

**Esperado:** `ping: local error: message too long, mtu=1420`, 100 % de pérdida.

**Comentario:** *"Al subir a 1400 bytes el sistema detecta el problema. En un escenario real de black hole, si los ICMP son bloqueados por un firewall intermedio, la aplicación no recibe ningún error, simplemente nunca llega la respuesta."*

### 2.3 Inducir el problema con observación en vivo

Tener Grafana visible en una ventana grande, dashboard refrescando cada 5 s, ventana de tiempo "Last 5 minutes".

```bash
# En otra terminal, mantener el pipeline corriendo en loop
cd ~/redato-hybrid-cloud
while true; do python3 pipeline/ml_pipeline.py; sleep 5; done
```

**Comentario:** *"Dejamos el pipeline corriendo en loop para generar tráfico continuo a través del túnel."*

```bash
# Inducir el black hole
sudo ip link set wg0 mtu 576
sudo iptables -I OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP
sudo iptables -I FORWARD -p icmp --icmp-type fragmentation-needed -j DROP
echo "MTU reducida a 576 y ICMP bloqueado"
```

**Comentario, mirando el dashboard:** *"Ahora bajamos la MTU del túnel a 576 bytes y bloqueamos los mensajes ICMP de Fragmentation Needed con iptables. Esperemos 15–20 segundos y miremos el dashboard."*

**Qué señalar en el dashboard a medida que cambian las métricas:**
- **Capa 3 (RTT):** *"El RTT subió de ~1 ms a picos de 200–300 ms. La VPN sigue conectada pero el camino se degradó."*
- **Capa 4 (retransmisiones TCP):** *"Acá aparecen las retransmisiones. Antes estaban en cero, ahora se ven picos. El TCP intenta reenviar paquetes que se están perdiendo silenciosamente."*
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

**Comentario:** *"El MSS clamping intercepta el handshake TCP —los paquetes SYN y SYN-ACK— y ajusta el campo Maximum Segment Size para que nunca supere la MTU del túnel. La aplicación no se entera, el fix es transparente y no depende de que los ICMP lleguen."*

### 2.5 Mostrar la recuperación en el dashboard

**Comentario, esperando 15 s y mirando Grafana:** *"En el siguiente intervalo de scrape, las retransmisiones de capa 4 vuelven a cero. El RTT se normaliza. El pipeline de ML sigue descargando sin perder ningún byte. La recuperación es inmediata, visible en el mismo dashboard que usamos para diagnosticar."*

---

## Cierre (1–2 minutos)

**Comentario:** *"Lo que vimos: una arquitectura Hybrid Cloud completa con VPN WireGuard como enlace, un service mesh con balanceo cross-cluster y mTLS, un pipeline real de Machine Learning consumiendo datos desde Azure on-demand, y un observatorio multi-capa que permite ver un problema clásico de redes simultáneamente en cuatro capas OSI y aplicar la mitigación en vivo. Todas las capas del modelo OSI relevantes para Hybrid Cloud, integradas en una sola maqueta funcional."*

---

## Limpieza post-demo

Si terminás la defensa y querés dejar todo limpio para más tarde:

```bash
# Restaurar todo
sudo ip link set wg0 mtu 1420
sudo iptables -D OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP 2>/dev/null || true
sudo iptables -D FORWARD -p icmp --icmp-type fragmentation-needed -j DROP 2>/dev/null || true
sudo iptables -t mangle -F

# Matar el loop del pipeline
kill %1 2>/dev/null || true

# Matar exporters si querés
sudo pkill blackbox_exporter
pkill node_exporter
```

---

## Plan B — si algo falla en vivo

| Problema | Solución rápida |
|---|---|
| Kiali no muestra el grafo | `kubectl delete secret istio-remote-secret-cluster-b -n istio-system --context=cluster-a` y refrescar |
| El balanceo solo muestra v1 | Reiniciar helloworld-v2 en la Mac: `kubectl rollout restart deploy/helloworld-v2 -n sample --context=cluster-b` |
| Grafana no muestra datos | Verificar que Prometheus tiene los targets `up`: `curl localhost:9090/api/v1/targets` |
| El pipeline falla con timeout de Azure | Re-ejecutarlo: probablemente el SAS token o la conexión cayeron un segundo |
| WireGuard muestra `latest handshake` viejo | `sudo systemctl restart wg-quick@wg0` o reconectar Tailscale |

---

## Notas finales

- **Hablar mientras corre el pipeline**, no quedarse callado mirando el output.
- **No leer los comandos**, explicarlos: *"esto baja la MTU"*, *"esto bloquea los ICMP"*.
- **Señalar el dashboard con el cursor** mientras se explica qué cambia y por qué.
- **Si una métrica tarda en aparecer**, decir *"esperamos al próximo scrape de Prometheus"* — está bien que se note que es un sistema real.
- **Tener una segunda terminal con `~/startup-hybrid-cloud.sh`** lista por si Kiali rompe algo.
