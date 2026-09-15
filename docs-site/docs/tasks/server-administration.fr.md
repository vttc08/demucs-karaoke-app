# Administration du serveur { #server-administration }

Cette page couvre les configurations liées au réseau pour restreindre l'accès, la connexion à un service Demucs à distance, le routage des téléchargements via un proxy et la surveillance de l'application.

## Sommaire { #contents }

- [Restrict access to Guest Wi-Fi users](#restrict-access-to-guest-wi-fi-users)
- [Expose a remote Demucs service](#expose-a-remote-demucs-service)
- [Use a proxy server for downloads](#use-a-proxy-server-for-downloads)
- [Server Monitoring](#server-monitoring)

## Restreindre l'accès aux utilisateurs du Wi-Fi invité { #restrict-access-to-guest-wi-fi-users }

L'application est destinée à fonctionner sur un réseau local. Par défaut, toute personne connectée au même réseau peut y accéder. Au lieu de connecter les clients au même réseau local que les ordinateurs personnels, la plupart des routeurs à domicile, y compris les routeurs fournis par ISP, peuvent créer un réseau WiFi invité isolé.

Une connexion Wi-Fi peut également aider à restreindre l'accès à l'application karaoké. Vous pouvez accéder à l'application par l'intermédiaire de l'adresse Internet, tandis que le proxy inverse ne permet que les demandes provenant du réseau domestique.

??? note "Requires a public IP address and hairpin NAT"

    Si le routeur ne prend pas en charge le NAT loopback ou si le fournisseur d’accès utilise le CGNAT, utilisez plutôt l’une des [solutions d’accès distant](#expose-a-remote-demucs-service).

### Comment fonctionne cette configuration { #how-this-setup-works }

1. Pointez un enregistrement DNS à l'adresse IP publique du réseau d'accueil.
2. Configurer un proxy inverse pour autoriser les requêtes du sous-réseau d'accueil et refuser d'autres adresses IP.
3. Connectez les appareils invités au réseau WiFi invité isolé.

Avec le hairpin NAT, une demande de Guest Wi-Fi à l'adresse publique DNS est envoyée par le routeur ou la passerelle et de retour dans le réseau d'accueil. Du point de vue du proxy inverse, la demande provient du routeur, qui est inclus dans la liste d'autorisation.

Cela fournit une forte limite d'accès pour une installation de karaoké à domicile parce que les invités doivent être physiquement présents sur le réseau approuvé pour atteindre l'application.

### Configurer la page restreinte d'accès { #configure-the-access-restricted-page }

L’application inclut une page `/access-restricted` qui peut afficher un message aux utilisateurs refusés. Vous pouvez également configurer le proxy inverse pour afficher une page personnalisée.

![Access denied page](../assets/images/sysadmin/access-denied.webp)

La configuration générale du proxy inverse devrait :

- Autoriser le sous-réseau d'origine et refuser toutes les autres adresses IP.
- Transférer le trafic vers l'adresse IP et le port de l'application karaoké.
- Explicitly allow all requests to `/access-restricted` and forward that path to the application.
- Redirect reverse-proxy-generated `403` responses to `/access-restricted`.

Dans Nginx Proxy Manager, par exemple, créez une liste d’accès, ajoutez le sous-réseau local comme `192.168.0.0/24`, autorisez-le, refusez toutes les autres adresses et appliquez la liste à l’hôte proxy.

??? note "Nginx Proxy Manager custom Nginx configuration"

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
        # Replace with your destination URL or path. { #replace-with-your-destination-url-or-path }
        return 302 https://<your-karaoke-domain>/access-restricted;
    }
    ```

??? note "Caddy configuration"

    Replace the hostname, application address, and home subnet with your own values. This example allows `/access-restricted` for everyone, allows the rest of the application only from the home subnet, and redirects other clients to the access-restricted page.

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

    Le filtre `remote_ip` vérifie l’adresse source vue par Caddy. Si un autre proxy ou tunnel se trouve devant Caddy, configurez les proxys approuvés et vérifiez que l’adresse du client est conservée avant d’utiliser cette liste blanche.

    Cette configuration bloque toutes les adresses IP situées en dehors du sous-réseau local. Les requêtes refusées reçoivent une réponse `403` et sont redirigées vers `/access-restricted`, qui reste accessible à tous.

### CGNAT et autres solutions de remplacement du réseau { #cgnat-and-other-network-alternatives }

The configuration above requires both hairpin NAT and a public IP address. If the ISP uses CGNAT, use a free VPS, [Tailscale Funnel or Cloudflare Tunnel](#expose-a-remote-demucs-service) to handle the reverse proxy and access control. You may also need to update the reverse proxy allowlist when your WAN IP changes.

## Exposer un service de Demucs à distance { #expose-a-remote-demucs-service }

Vous pouvez utiliser l'ordinateur d'un ami avec un GPU pour exécuter le service Demucs, ou partager votre propre GPU avec eux. L'application karaoké doit être en mesure de se connecter au service Demucs distant ; le tunnel Cloudflare et Tailscale sont deux façons possibles de fournir cette connexion.

Les performances dépendent fortement des deux connexions Internet. Le traitement peut être plus lent lorsque la connexion Tailscale est relayée. Utilisez la page de test de débit `/transfer` de Demucs pour vérifier les vitesses d’envoi et de téléchargement, puis ajustez le [seuil de traitement direct des médias](../configuration/karaoke-processing.md#separation-direct-media-cutoff-mb).

![Demucs speed test](../assets/images/sysadmin/demucs-speedtest.webp)

### Tunnel Cloudflare { #cloudflare-tunnel }

!!! warning "Protéger les services Demucs exposés publiquement"

    Une clé API est fortement recommandée dès que le service Demucs est exposé sur Internet. Configure the same key in the [Demucs service](../configuration/environments.md#service-paths-and-access) and the [Karaoke application](../configuration/karaoke-processing.md#separation-service-api-key), then test the connection with [Check Demucs](../configuration/tools.md#check-demucs).

    Cloudflare Tunnel can be used without registering a domain when a temporary random hostname is sufficient. Using your own domain requires a Cloudflare-managed domain and additional tunnel configuration, see [Cloudflare Tunnel with Docker from Homelab Haven](https://homelabhaven.com/posts/remote-access-2-cloudflare-tunnel-docker/).

### Install `cloudflared` { #install-cloudflared }

Use the official [Cloudflare downloads page](https://developers.cloudflare.com/tunnel/downloads/) for the latest packages and binaries. The examples below install the connector; you still need to create a named tunnel and configure its hostname and origin in Cloudflare.

=== "Windows"

    1. Download the 64-bit MSI or executable from the [Cloudflare downloads page](https://developers.cloudflare.com/tunnel/downloads/).
    2. If you downloaded the executable, rename it to `cloudflared.exe` and place it in a directory on your `PATH`, such as `C:\Cloudflared\bin`.
    3. Ouvrez PowerShell et vérifiez l'installation:

        ```powershell
        cloudflared.exe --version
        ```

Les installations de Windows ne sont pas mises à jour automatiquement. Téléchargez une version plus récente manuellement au besoin.

=== "macOS"

    Install with [Homebrew](https://brew.sh/):

    ```bash
    brew install cloudflared
    cloudflared --version
    ```

    To install the connector as a macOS service after creating a named tunnel, use `cloudflared service install` for a login agent or `sudo cloudflared service install` for a launch daemon.

=== "Linux"

Sur Debian ou Ubuntu, installer depuis le dépôt de paquets de Cloudflare :

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

    For RPM-based distributions, Arch Linux, or direct binary downloads, use the [official download instructions](https://developers.cloudflare.com/tunnel/downloads/). After creating a named tunnel, install the systemd service with `sudo cloudflared service install`.

=== "Docker"

Tirez l'image officielle et vérifiez :

    ```bash
    docker pull cloudflare/cloudflared:latest
    docker run --rm cloudflare/cloudflared:latest version
    ```

Pour un tunnel géré à distance, copiez la commande d'installation à partir du tableau de bord Cloudflare. Un exemple de Compose basé sur un jeton est :

    ```yaml
    services:
      cloudflared:
        image: cloudflare/cloudflared:latest
        restart: unless-stopped
        command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    ```

### Créer et exécuter le tunnel { #create-and-run-the-tunnel }

1. In the Cloudflare dashboard, open **Networking → Tunnels**, create a tunnel, and choose `cloudflared`.
2. Add a public hostname and point it to the local origin, such as `http://<your-application-ip>:8000` for the karaoke application or `http://<your-demucs-ip>:8001` for Demucs.
3. Exécutez le connecteur, la commande est :

    ```bash
    cloudflared tunnel --no-autoupdate run --token <TUNNEL_TOKEN>
    ```

4. Protégez le paramètre Demucs avec une clé API et configurez la même clé dans les deux services.

??? note "Quick tunnels are for testing only"

    A quick tunnel creates a random `trycloudflare.com` hostname without requiring a Cloudflare account. It is useful for a short connectivity test, but it is not suitable for production karaoke: Cloudflare documents a 200-request concurrency limit and no Server-Sent Events support.

    ```bash
    cloudflared tunnel --url http://localhost:<port>
    ```

!!! warning "Cloudflare CDN upload limit"

    Cloudflare CDN has a **hard limit of 100 MB** for file uploads. Set the [separation direct media cutoff](../configuration/karaoke-processing.md#separation-direct-media-cutoff-mb) to `100` MB or lower. Otherwise, karaoke processing for larger video files will fail.

### Échelle de queue { #tailscale }

Tailscale creates a mesh network between the karaoke application and the remote Demucs service. [Share your machine with other users](https://tailscale.com/docs/features/sharing) when the Demucs host belongs to another person.

1. Install [Tailscale](https://tailscale.com/download) on both machines.
2. Connectez-vous au même compte ou rejoignez le même réseau.
3. Find the Demucs service's Tailscale IP address in the admin console or with `tailscale status`.
4. Set the application's [separation service URL](../configuration/karaoke-processing.md#separation-service-url) to the Tailscale IP address and port of the Demucs service.
5. Test the connection and run the Demucs `/transfer` speed test.

Tailscale works best with a direct connection. See the [connection-type guidance](https://tailscale.com/docs/reference/connection-types#home-and-small-office-networks) and [firewall guidance](https://tailscale.com/docs/integrations/firewalls#firewall-compatibility-and-workarounds) to improve direct connectivity.

## Utilisez un serveur proxy pour les téléchargements { #use-a-proxy-server-for-downloads }

The application supports a [proxy server](../configuration/downloads.md#yt-dlp-proxy-url) for downloading videos from YouTube. A proxy can help when a home network is temporarily blocked or rate-limited by YouTube.

For more advanced routing, use a dashboard such as [Mihomo with metacubexd](https://github.com/metacubex/metacubexd) to add, manage, and switch between multiple proxy servers.

![Mihomo dashboard](../assets/images/sysadmin/mihomo-dashboard.webp)

### Proxy simple SOCKS5 { #simple-socks5-proxy }

Cloudflare WARP is one option for creating a proxy. The [warproxy Docker image](https://github.com/kingcc/warproxy) converts Cloudflare WARP into a SOCKS5 egress proxy.

Testez un proxy local SOCKS5 avec :

```bash
curl -4 -x socks5://localhost:1080 https://ifconfig.me
# A Cloudflare WARP proxy should return a 104.x.x.x IPv4 address. { #a-cloudflare-warp-proxy-should-return-a-104xxx-ipv4-address }
```

To convert a commercial, WireGuard, or OpenVPN endpoint into a SOCKS5 proxy, see [gluetun](https://github.com/passteque/gluetun) and its [HTTP proxy configuration](https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/http-proxy.md).

### Mihomo et metacubexd { #mihomo-and-metacubexd }

L'application prend actuellement en charge un serveur proxy configuré et ne fournit pas de commutation de proxy ou d'équilibrage de charge. Mihomo peut fournir ces fonctionnalités sans exiger le réglage proxy de l'application karaoké pour changer.

Configurer Mihomo avec un proxy HTTP entrant, puis ajouter et gérer plusieurs serveurs proxy en amont à travers son tableau de bord.

??? note "Mihomo and metacubexd basic setup"

    Exemple de configuration Docker Composez :

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

    Review the [Mihomo configuration](https://wiki.metacubex.one/en/config/) and add your proxy servers. A basic example is:

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

    Open `http://<your-server-ip>:8080` and use `change-me-clash` to access the dashboard. Replace all example secrets before using this configuration.

    Après avoir configuré le proxy, passez à un autre serveur proxy du tableau de bord metacubexd si un téléchargement yt-dlp échoue. Le paramètre proxy de l'application karaoké n'a pas besoin de changer.

## Surveillance du serveur { #server-monitoring }

Pour l'application principale, vous pouvez identifier les problèmes ou les erreurs de configuration en vérifiant les journaux.

If you run the application with `uvicorn` in the foreground or in a tmux session, its logs are shown in the terminal.

Pour Linux avec systemd, utilisez :

```bash
sudo journalctl -u your-karaoke-service-name -f
```

Pour Docker, utiliser:

```bash
docker logs -f your-karaoke-container-name
# Or: docker compose logs -f { #or-docker-compose-logs-f }
```

The application also logs the specific `yt-dlp` download commands, which can help trace download failures.

Pour le service Demucs, les journaux Demucs et WhisperX sont affichés dans le terminal. Par exemple:

```text
2026-09-12 14:43:34 - whisperx.asr - INFO - No language specified, language will be detected for each audio file (increases inference time)
2026-09-12 14:43:34 - whisperx.vads.pyannote - INFO - Performing voice activity detection using Pyannote..
2026-09-12 14:43:39 - whisperx.asr - INFO - Detected language: en (0.88) in first 30s of audio
started inference
Inference time for segment 0: 0.78 seconds
```

The Demucs service also exposes a `/metrics` endpoint that you can monitor with an external tool.

```json
{"service":"demucs","snapshot_at":"2026-09-12T21:58:47.346862+00:00","active_job_count":0,"running_job_count":0,"active_job_counts_by_status":{},"active_job_counts_by_kind":{},"free_vram_bytes":11013193728,"total_vram_bytes":12878086144,"last_gc_at":"2026-09-12T21:48:58.140879+00:00","last_gc_mode":"full","last_gc_detail":"Released WhisperX caches and CUDA memory","active_jobs":[]}
```

Sur Windows, la meilleure façon de surveiller l'application ou les tâches bloquées de débogage est d'utiliser Task Manager et de vérifier le graphique GPU pour l'utilisation de VRAM et GPU.

![Windows Task Manager showing GPU usage](../assets/images/sysadmin/task-manager.webp)

Task Manager is not available on a phone. For this use case, use [RustDesk](https://rustdesk.com/) to remotely access the Windows desktop.
