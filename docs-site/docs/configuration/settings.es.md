# Página de ajustes

!!! note "La página de ajustes es solo para administradores"

    La página de ajustes está disponible solo después de iniciar sesión como administrador. Cree una cuenta de administrador durante la configuración inicial.

![Página de ajustes](../assets/images/settings.webp){ width="800" }

Use los [ajustes recomendados](#recommended-settings) como punto de partida y, después, lea las guías de cada sección para obtener más detalles.

<div class="grid cards" markdown>
-   __[Procesamiento de karaoke](karaoke-processing.md)__

    ---

    Configure el motor de separación, el formato de salida y los límites de procesamiento.

-   __[Letras de WhisperX](whisperx-lyrics.md)__

    ---

    Configure la transcripción, la alineación, la sincronización temporal y la precarga de modelos.

-   __[Rutas de la aplicación](application-paths.md)__

    ---

    Elija las ubicaciones de medios, caché y ejecutables.

-   __[Descargas](downloads.md)__

    ---

    Ajuste las descargas de yt-dlp, el enrutamiento por proxy, la búsqueda simultánea y los proveedores de letras.

-   __[Escenario](stage.md)__

    ---

    Configure enlaces del escenario, reproducción en espera y la mezcla de voces predeterminada.

-   __[Herramientas](tools.md)__

    ---

    Inspeccione la conectividad y el almacenamiento, actualice yt-dlp o libere memoria de Demucs remoto.
</div>

## Ajustes recomendados { #recommended-settings }

Los siguientes valores son un buen punto de partida para disfrutar de karaoke sin problemas. Ajústelos según su hardware, red y flujo de trabajo preferido.

### Procesamiento de karaoke

- **Motor de separación:** `demucs`. Si el backend de Demucs no tiene acceso a una GPU, use `Sherpa+Spleeter` en su lugar.
- **Límite directo de medios (MB):** `500`. Redúzcalo, por ejemplo a `20–50`, si la conexión de red a Demucs es lenta.
- **Tasa de bits de stems MP3**: `320`. Redúzcala, por ejemplo a `128-160`, si la conexión de red a Demucs es lenta.

### Letras de WhisperX

- **Detectar idioma antes de la alineación:** activado.
- **Usar sincronización temporal de las letras:** desactivado.

### Descargas

- **Búsqueda paralela en YouTube:** activada.

### Escenario

- **URL QR del escenario:** configure una URL para su propia página de cola.
- **URL de medios de espera del escenario:** configure su propia ruta de medios o caché para la pantalla de espera con la cola vacía.

Estas recomendaciones funcionan bien en una amplia variedad de configuraciones, pero puede ajustarlas en cualquier momento desde la página de ajustes.
