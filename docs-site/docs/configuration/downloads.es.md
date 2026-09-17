# Descargas

![Configuración de descargas](../assets/images/settings/downloads.webp){ width="400" }

Use esta sección para controlar las preferencias de descarga de yt-dlp, el enrutamiento mediante proxy, la búsqueda simultánea y los proveedores de letras. Estos ajustes también se pueden configurar mediante [variables de entorno](environments.md) cuando una implementación necesita valores fijos.

### Códec de vídeo de yt-dlp { #yt-dlp-video-codec }

Una preferencia opcional de códec de vídeo para yt-dlp. Déjela vacía para usar la selección predeterminada de yt-dlp.

Los navegadores de los dispositivos Apple tienen compatibilidad limitada con códecs; establézcala en `avc` si hay problemas de reproducción de vídeo.

### Resolución de vídeo de yt-dlp

La resolución máxima preferida del vídeo. Elija `Default` para conservar el comportamiento actual, o seleccione `360p`, `480p`, `720p`, `1080p` o `2160p` para limitar las descargas de vídeo a esa resolución o inferior.

### URL de proxy de yt-dlp { #yt-dlp-proxy-url }

Una URL de proxy opcional para yt-dlp y solicitudes salientes relacionadas. Se admiten URL de proxy HTTP, HTTPS, SOCKS4 y SOCKS5. Déjela vacía para conectarse directamente.

### Versión de yt-dlp

Use **Comprobar versión** para mostrar la versión instalada de yt-dlp. **Actualizar yt-dlp** instala la versión estable, mientras que **Instalar yt-dlp Nightly** instala la versión nocturna. Actualice yt-dlp cuando cambie un proveedor o cuando la versión actual deje de funcionar con una fuente de vídeo.

### Búsqueda paralela en YouTube { #parallel-youtube-search }

Busca la consulta original y una variante de karaoke al mismo tiempo. Puede devolver resultados más útiles, pero genera solicitudes salientes adicionales.

### Proveedores de letras

Active o desactive los proveedores de letras integrados:

- **Letras de NetEase**
- **Letras de LRCLIB**

Desactive un proveedor cuando no esté disponible o cuando no desee utilizarlo durante las búsquedas de letras.
