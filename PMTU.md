# Demo PMTU Black Hole — Guion para la defensa

## Contexto

El **Path MTU Discovery (PMTUD)** es el mecanismo definido en el RFC 1191 por el cual un host TCP determina el tamaño máximo de paquete que puede enviar por un camino sin que sea fragmentado. Funciona enviando paquetes con el bit **DF (Don't Fragment)** activado y esperando mensajes ICMP **Fragmentation Needed** (RFC 792) si algún router intermedio no puede reenviar el paquete.

El **PMTU black hole** ocurre cuando esos mensajes ICMP son descartados (por un firewall mal configurado, por ejemplo), y el host emisor queda esperando ACKs que nunca llegan, sin recibir ningún error explícito. La conexión TCP se cuelga silenciosamente.

En una arquitectura Hybrid Cloud con VPN WireGuard, este problema es especialmente relevante porque el túnel encapsula los paquetes, reduciendo la MTU efectiva. Si la aplicación intenta enviar segmentos TCP más grandes que la MTU del túnel y los mensajes ICMP de notificación son bloqueados, la conexión se congela sin que la aplicación lo sepa.

---

## Topología

```
[Cluster A — on-prem]          túnel WireGuard            [Cluster B — cloud]
   10.100.0.1 (wg0)     ←————————————————————————→     10.100.0.2 (utun7)
     MTU: 1420                                              MTU: 1420
```

---

## Paso 1 — Baseline normal

Mostrar que el túnel funciona correctamente con paquetes que caben en la MTU.

```bash
ping -M do -s 1372 10.100.0.2 -c 3
```

**Salida esperada:**
```
1380 bytes from 10.100.0.2: icmp_seq=1 ttl=64 time=26ms
1380 bytes from 10.100.0.2: icmp_seq=2 ttl=64 time=15ms
1380 bytes from 10.100.0.2: icmp_seq=3 ttl=64 time=31ms
0% packet loss
```

**Qué decir:** *"El túnel WireGuard funciona correctamente. Enviamos paquetes de 1372 bytes de payload con el bit DF activado — el tamaño total con headers IP es 1400 bytes, que entra dentro de la MTU de 1420 del túnel."*

---

## Paso 2 — Reproducir el problema PMTU

Aumentar el tamaño del paquete para que supere la MTU del túnel.

```bash
ping -M do -s 1400 10.100.0.2 -c 3
```

**Salida esperada:**
```
ping: local error: message too long, mtu=1420
ping: local error: message too long, mtu=1420
ping: local error: message too long, mtu=1420
100% packet loss
```

**Qué decir:** *"Al intentar enviar 1400 bytes de payload (1428 bytes totales con headers), el paquete no cabe en el túnel. El sistema detecta el problema, pero en un escenario real de PMTU black hole, si los mensajes ICMP Fragmentation Needed (definidos en RFC 792) son bloqueados por un firewall intermedio, la aplicación no recibe ningún error — el TCP simplemente se queda esperando ACKs que nunca llegan. La conexión se congela silenciosamente."*

---

## Paso 3 — Diagnóstico por capas OSI

Capturar tráfico para mostrar el mecanismo a nivel de protocolo.

```bash
# En otra terminal — capturar ICMP sobre el túnel
sudo tcpdump -i wg0 -n icmp &

# Provocar el problema
ping -M do -s 1400 10.100.0.2 -c 2
```

**Qué mostrar:**
- **Capa 3 (Red):** el paquete IP tiene el bit DF activado y supera la MTU → el sistema genera un mensaje ICMP tipo 3, código 4 (Destination Unreachable, Fragmentation Needed)
- **Capa 4 (Transporte):** TCP no puede establecer sesión con segmentos grandes porque el SYN/SYN-ACK no llega si el paquete es demasiado grande
- **Relación con RFCs:** RFC 791 (bit DF en IP), RFC 792 (ICMP Fragmentation Needed), RFC 1191 (Path MTU Discovery), RFC 2923 (TCP Problems with PMTUD)

```bash
# Detener tcpdump
kill %1
```

---

## Paso 4 — Aplicar el fix: MSS Clamping

El **MSS clamping** es la solución estándar. Ajusta automáticamente el campo MSS (Maximum Segment Size) en el handshake TCP para que nunca supere la MTU del túnel, sin necesidad de depender de los mensajes ICMP.

```bash
# Verificar que el clamping está activo
sudo iptables -t mangle -L | grep TCPMSS
```

**Salida esperada:**
```
TCPMSS  tcp  --  anywhere  anywhere  tcp flags:SYN,RST/SYN  TCPMSS clamp to PMTU
TCPMSS  tcp  --  anywhere  anywhere  tcp flags:SYN,RST/SYN  TCPMSS clamp to PMTU
```

**Qué decir:** *"Con MSS clamping activado en iptables, el kernel intercepta el handshake TCP (los paquetes SYN y SYN-ACK) y reduce el campo MSS al valor que cabe en el túnel. Esto ocurre de forma transparente para la aplicación, sin cambios en el código ni en la configuración del servidor."*

Verificar recuperación:
```bash
ping -M do -s 1372 10.100.0.2 -c 3
```

**Salida esperada:**
```
0% packet loss — recuperación inmediata
```

**Qué decir:** *"La conexión se recupera sin tocar la aplicación. El MSS clamping es la solución recomendada para VPNs y túneles en producción, precisamente porque no depende de que los mensajes ICMP lleguen correctamente."*

---

## Comandos de limpieza post-demo

```bash
# Restaurar MTU original del túnel
sudo ip link set wg0 mtu 1420

# Limpiar reglas iptables de la demo
sudo iptables -D OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP 2>/dev/null || true
sudo iptables -D FORWARD -p icmp --icmp-type fragmentation-needed -j DROP 2>/dev/null || true
```

---

## Referencias

- RFC 791 — Internet Protocol (bit Don't Fragment)
- RFC 792 — Internet Control Message Protocol (Fragmentation Needed)
- RFC 1191 — Path MTU Discovery
- RFC 2923 — TCP Problems with Path MTU Discovery
- RFC 4821 — Packetization Layer Path MTU Discovery
