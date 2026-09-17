# Administración del servidor

Esta página describe configuraciones de red para restringir el acceso, conectarse a un servicio Demucs remoto, enrutar descargas mediante un proxy y supervisar la aplicación.

## Contenido

- [Restringir el acceso de usuarios de Wi-Fi para invitados](#restringir-el-acceso-de-usuarios-de-wi-fi-para-invitados)
- [Exponer un servicio Demucs remoto](#expose-a-remote-demucs-service)
- [Usar un servidor proxy para las descargas](#use-a-proxy-server-for-downloads)
- [Supervisión del servidor](#server-monitoring)

## Restringir el acceso de usuarios de Wi-Fi para invitados

La aplicación está pensada para ejecutarse en una red local. De forma predeterminada, cualquiera conectado a esa red puede acceder a ella. En vez de conectar a los invitados a la misma LAN que los ordenadores personales, la mayoría de los routers domésticos, incluidos los proporcionados por ISP, pueden crear una red Wi-Fi de invitados aislada.

La Wi-Fi de invitados también puede ayudar a restringir el acceso a la aplicación de karaoke. Los invitados acceden mediante la dirección expuesta a Internet, mientras que el proxy inverso permite únicamente solicitudes procedentes de la red doméstica.

??? note "Requiere una IP pública y NAT hairpin"

    Si el router no admite NAT hairpin, o el ISP usa CGNAT, utiliza una de las [alternativas de acceso remoto](#expose-a-remote-demucs-service).

### Cómo funciona esta configuración

1. Dirige un registro DNS a la IP pública de la red doméstica.
2. Configura un proxy inverso para permitir solicitudes desde la subred doméstica y denegar otras direcciones IP.
3. Conecta los dispositivos de invitados a la red Wi-Fi de invitados aislada.

Con NAT hairpin, una solicitud desde la Wi-Fi de invitados a la dirección DNS pública se envía a través del router o puerta de enlace y vuelve a la red doméstica. Desde el punto de vista del proxy inverso, la solicitud procede del router, que está incluido en la lista de permitidos. Las solicitudes de usuarios aleatorios de Internet se deniegan.

Esto proporciona un sólido límite de acceso para una instalación doméstica de karaoke, porque los invitados deben estar físicamente presentes en la red aprobada para acceder a la aplicación.

### Configura la página de acceso restringido

La aplicación incluye una página `/access-restricted` que puede mostrar un mensaje a los usuarios denegados. También puedes configurar el proxy inverso para mostrar una página personalizada.

![Página de acceso denegado](../assets/images/sysadmin/access-denied.webp)

La configuración general del proxy inverso debe:

- Permitir la subred doméstica y denegar todas las demás direcciones IP.
- Reenviar el tráfico permitido a la dirección IP y el puerto de la aplicación de karaoke.
- Permitir explícitamente todas las solicitudes a `/access-restricted` y reenviar esa ruta a la aplicación.
- Redirigir las respuestas `403` generadas por el proxy inverso a `/access-restricted`.

Por ejemplo, en Nginx Proxy Manager, crea una Access List, añade la subred doméstica, como `192.168.0.0/24`, permítela, deniega las demás direcciones y aplica la lista al host proxy.

??? note "Configuración Nginx personalizada de Nginx Proxy Manager"

    ```nginx
    location /access-restricted {
        allow all;
        proxy_pass http://<your-application-ip>:<your-application-port>;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    error_page 403 = @handle_403;

    location @handle_403 {
        # Replace with your destination URL or path.
        return 302 https://<your-karaoke-domain>/access-restricted;
    }
    ```

??? note "Configuración de Caddy"

    Sustituye el nombre de host, la dirección de la aplicación y la subred doméstica por tus propios valores. Este ejemplo permite `/access-restricted` a todo el mundo, permite el resto de la aplicación solo desde la subred doméstica y redirige a los demás clientes a la página de acceso restringido.

    ```caddyfile
    your-karaoke-domain.example {
        route {
            @access_restricted path /access-restricted*
            handle @access_restricted {
                reverse_proxy http://<your-application-ip>:<your-application-port>
            }

            @outside_home not remote_ip 192.168.0.0/24
            handle @outside_home {
                redir /access-restricted 302
            }

            handle {
                reverse_proxy http://<your-application-ip>:<your-application-port>
            }
        }
    }
    ```

    El comparador `remote_ip` verifica la dirección de origen que ve Caddy. Si hay otro proxy o túnel delante de Caddy, configura proxies de confianza y confirma que se conserva la dirección del cliente antes de depender de esta lista de permitidos.

Esta configuración bloquea todas las direcciones IP fuera de la subred doméstica. Las solicitudes denegadas reciben una respuesta `403` y se redirigen a `/access-restricted`, que sigue disponible para todos.

### CGNAT y otras alternativas de red

La configuración anterior requiere tanto NAT hairpin como una dirección IP pública. Si el ISP usa CGNAT, utiliza un VPS gratuito, [Tailscale Funnel o Cloudflare Tunnel](#expose-a-remote-demucs-service) para gestionar el proxy inverso y el control de acceso. También puedes tener que actualizar la lista de permitidos del proxy cuando cambie tu IP WAN.

## Exponer un servicio Demucs remoto { #expose-a-remote-demucs-service }

Puedes usar el ordenador de un amigo con GPU para ejecutar el servicio Demucs, o compartir tu propia GPU con esa persona. La aplicación de karaoke debe poder conectarse al servicio Demucs remoto; Cloudflare Tunnel y Tailscale son dos formas posibles de proporcionar esa conexión.

El rendimiento depende en gran medida de ambas conexiones a Internet. El procesamiento puede ser más lento si una conexión Tailscale se retransmite. Usa la página de prueba de velocidad `/transfer` de Demucs para comprobar el rendimiento de carga y descarga y ajusta el [límite de contenido directo para separación](../configuration/karaoke-processing.md#separation-direct-media-cutoff-mb) según corresponda.

![Prueba de velocidad de Demucs](../assets/images/sysadmin/demucs-speedtest.webp)

### Cloudflare Tunnel

!!! warning "Protege los servicios Demucs expuestos públicamente"

    Se recomienda encarecidamente una clave de API cuando el servicio Demucs se expone a Internet. Configura la misma clave en el [servicio Demucs](../configuration/environments.md#service-paths-and-access) y la [aplicación Karaoke](../configuration/karaoke-processing.md#separation-service-api-key), y prueba la conexión con [Check Demucs](../configuration/tools.md#check-demucs).

Cloudflare Tunnel se puede usar sin registrar un dominio cuando basta un nombre de host temporal aleatorio. Usar tu propio dominio requiere un dominio gestionado por Cloudflare y configuración adicional del túnel; consulta [Cloudflare Tunnel with Docker from Homelab Haven](https://homelabhaven.com/posts/remote-access-2-cloudflare-tunnel-docker/).

### Instalar `cloudflared`

Consulta la [página oficial de descargas de Cloudflare](https://developers.cloudflare.com/tunnel/downloads/) para los paquetes y binarios más recientes. Los ejemplos siguientes instalan el conector; aún debes crear un túnel con nombre y configurar su nombre de host y origen en Cloudflare.

=== "Windows"

    1. Descarga el MSI de 64 bits o el ejecutable desde la [página de descargas de Cloudflare](https://developers.cloudflare.com/tunnel/downloads/).
    2. Si descargaste el ejecutable, cámbiale el nombre a `cloudflared.exe` y colócalo en un directorio de tu `PATH`, como `C:\Cloudflared\bin`.
    3. Abre PowerShell y verifica la instalación:

        ```powershell
        cloudflared.exe --version
        ```

    Las instalaciones de Windows no se actualizan automáticamente. Descarga manualmente una versión más reciente cuando sea necesario.

=== "macOS"

    Instala con [Homebrew](https://brew.sh/):

    ```bash
    brew install cloudflared
    cloudflared --version
    ```

    Para instalar el conector como servicio de macOS después de crear un túnel con nombre, usa `cloudflared service install` para un agente de inicio de sesión o `sudo cloudflared service install` para un daemon de lanzamiento.

=== "Linux"

    En Debian o Ubuntu, instala desde el repositorio de paquetes de Cloudflare:

    ```bash
    sudo mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
      | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
      | sudo tee /etc/apt/sources.list.d/cloudflared.list
    sudo apt-get update
    sudo apt-get install cloudflared
    cloudflared --version
    ```

    Para distribuciones basadas en RPM, Arch Linux o descargas directas de binarios, usa las [instrucciones oficiales de descarga](https://developers.cloudflare.com/tunnel/downloads/). Después de crear un túnel con nombre, instala el servicio systemd con `sudo cloudflared service install`.

=== "Docker"

    Descarga la imagen oficial y verifícala:

    ```bash
    docker pull cloudflare/cloudflared:latest
    docker run --rm cloudflare/cloudflared:latest version
    ```

    Para un túnel administrado remotamente, copia el comando de instalación del panel de Cloudflare. Un ejemplo de Compose basado en token es:

    ```yaml
    services:
      cloudflared:
        image: cloudflare/cloudflared:latest
        restart: unless-stopped
        command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    ```

### Crear y ejecutar el túnel

1. En el panel de Cloudflare, abre **Networking → Tunnels**, crea un túnel y elige `cloudflared`.
2. Añade un nombre de host público y dirígelo al origen local, por ejemplo `http://<your-application-ip>:8000` para la aplicación de karaoke o `http://<your-demucs-ip>:8001` para Demucs.
3. Ejecuta el conector con este comando:

    ```bash
    cloudflared tunnel --no-autoupdate run --token <TUNNEL_TOKEN>
    ```

4. Protege el punto de acceso de Demucs con una clave de API y configura la misma clave en ambos servicios.

??? note "Los túneles rápidos son solo para pruebas"

    Un túnel rápido crea un nombre de host aleatorio `trycloudflare.com` sin requerir una cuenta de Cloudflare. Sirve para una prueba breve de conectividad, pero no es adecuado para karaoke en producción: Cloudflare documenta un límite de simultaneidad de 200 solicitudes y no admite Server-Sent Events.

    ```bash
    cloudflared tunnel --url http://localhost:<port>
    ```

!!! warning "Límite de subida de Cloudflare CDN"

    Cloudflare CDN tiene un **límite estricto de 100 MB** para subidas de archivos. Establece el [límite de contenido directo para separación](../configuration/karaoke-processing.md#separation-direct-media-cutoff-mb) en `100` MB o menos. De lo contrario, el procesamiento de karaoke de vídeos más grandes fallará.

### Tailscale

Tailscale crea una red de malla entre la aplicación de karaoke y el servicio Demucs remoto. [Comparte tu equipo con otros usuarios](https://tailscale.com/docs/features/sharing) cuando el host de Demucs pertenezca a otra persona.

1. Instala [Tailscale](https://tailscale.com/download) en ambos equipos.
2. Inicia sesión con la misma cuenta o únete a la misma tailnet.
3. Busca la dirección IP de Tailscale del servicio Demucs en la consola de administración o con `tailscale status`.
4. Configura la [URL del servicio de separación](../configuration/karaoke-processing.md#separation-service-url) de la aplicación con la dirección IP y el puerto de Tailscale del servicio Demucs.
5. Prueba la conexión y ejecuta la prueba de velocidad `/transfer` de Demucs.

Tailscale funciona mejor con una conexión directa. Consulta la [guía de tipos de conexión](https://tailscale.com/docs/reference/connection-types#home-and-small-office-networks) y la [guía de firewall](https://tailscale.com/docs/integrations/firewalls#firewall-compatibility-and-workarounds) para mejorar la conectividad directa.

## Usar un servidor proxy para las descargas { #use-a-proxy-server-for-downloads }

La aplicación admite un [servidor proxy](../configuration/downloads.md#yt-dlp-proxy-url) para descargar vídeos de YouTube. Un proxy puede ayudar cuando una red doméstica se bloquea temporalmente o YouTube limita su velocidad.

Para enrutamiento más avanzado, usa un panel como [Mihomo con metacubexd](https://github.com/metacubex/metacubexd) para añadir, gestionar y alternar entre varios servidores proxy.

![Panel de Mihomo](../assets/images/sysadmin/mihomo-dashboard.webp)

### Proxy SOCKS5 sencillo

Cloudflare WARP es una opción para crear un proxy. La [imagen Docker warproxy](https://github.com/kingcc/warproxy) convierte Cloudflare WARP en un proxy de salida SOCKS5.

Prueba un proxy SOCKS5 local con:

```bash
curl -4 -x socks5://localhost:1080 https://ifconfig.me
# A Cloudflare WARP proxy should return a 104.x.x.x IPv4 address.
```

Para convertir un punto de acceso comercial, WireGuard u OpenVPN en un proxy SOCKS5, consulta [gluetun](https://github.com/passteque/gluetun) y su [configuración de proxy HTTP](https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/http-proxy.md).

### Mihomo y metacubexd

Actualmente la aplicación admite un servidor proxy configurado y no proporciona alternancia ni equilibrio de carga de proxy. Mihomo puede ofrecer esas funciones sin que cambie el ajuste de proxy de la aplicación de karaoke.

Configura Mihomo con una entrada de proxy HTTP y luego añade y administra varios servidores proxy ascendentes mediante su panel.

??? note "Configuración básica de Mihomo y metacubexd"

    Ejemplo de configuración Docker Compose:

    ```yaml
    services:
      metacubexd:
        image: ghcr.io/metacubex/metacubexd-server:latest
        restart: unless-stopped
        environment:
          CONTROL_TOKEN: change-me-control
          CLASH_SECRET: change-me-clash
          CONTROL_PORT: "8080"
          CLASH_API_PORT: "9090"
          MIXED_PORT: "7890"
          TZ: Asia/Shanghai
        ports:
          - "8080:8080" # Dashboard UI and control agent API.
          - "9090:9090" # Mihomo Clash API and WebSocket.
          - "7890:7890" # Mixed proxy port.
        volumes:
          - metacubexd-data:/data

    volumes:
      metacubexd-data: {}
    ```

    Revisa la [configuración de Mihomo](https://wiki.metacubex.one/en/config/) y añade tus servidores proxy. Un ejemplo básico es:

    ```yaml
    external-controller: 0.0.0.0:9090
    secret: change-me-clash
    mixed-port: 7890
    allow-lan: true
    mode: rule
    log-level: info
    ipv6: false
    proxies:
      - name: Proxy1
    ```

    Abre `http://<your-server-ip>:8080` y usa `change-me-clash` para acceder al panel. Sustituye todos los secretos de ejemplo antes de usar esta configuración.

Después de configurar el proxy, cambia a otro servidor proxy desde el panel de metacubexd si falla una descarga de yt-dlp. No es necesario modificar el ajuste de proxy de la aplicación de karaoke.

## Supervisión del servidor { #server-monitoring }

Para la aplicación principal, puedes identificar problemas o configuraciones incorrectas revisando los registros.

Si ejecutas la aplicación con `uvicorn` en primer plano o en una sesión tmux, los registros aparecen en la terminal.

Para Linux con systemd, usa:

```bash
sudo journalctl -u your-karaoke-service-name -f
```

Para Docker, usa:

```bash
docker logs -f your-karaoke-container-name
# Or: docker compose logs -f
```

La aplicación también registra los comandos concretos de descarga de `yt-dlp`, que pueden ayudar a rastrear fallos de descarga.

Para el servicio Demucs, los registros relevantes de Demucs y WhisperX se muestran en la terminal. Por ejemplo:

```text
2026-09-12 14:43:34 - whisperx.asr - INFO - No language specified, language will be detected for each audio file (increases inference time)
2026-09-12 14:43:34 - whisperx.vads.pyannote - INFO - Performing voice activity detection using Pyannote..
2026-09-12 14:43:39 - whisperx.asr - INFO - Detected language: en (0.88) in first 30s of audio
started inference
Inference time for segment 0: 0.78 seconds
```

El servicio Demucs también expone un punto de acceso `/metrics` que puedes supervisar con una herramienta externa.

```json
{"service":"demucs","snapshot_at":"2026-09-12T21:58:47.346862+00:00","active_job_count":0,"running_job_count":0,"active_job_counts_by_status":{},"active_job_counts_by_kind":{},"free_vram_bytes":11013193728,"total_vram_bytes":12878086144,"last_gc_at":"2026-09-12T21:48:58.140879+00:00","last_gc_mode":"full","last_gc_detail":"Released WhisperX caches and CUDA memory","active_jobs":[]}
```

En Windows, la mejor forma de supervisar la aplicación o depurar trabajos bloqueados es usar el Administrador de tareas y revisar el gráfico de GPU para ver el uso de VRAM y GPU.

![Administrador de tareas de Windows mostrando uso de GPU](../assets/images/sysadmin/task-manager.webp)

El Administrador de tareas no está disponible en un teléfono. Para este caso, usa [RustDesk](https://rustdesk.com/) para acceder remotamente al escritorio de Windows.
