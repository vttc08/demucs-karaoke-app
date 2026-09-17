# Tareas de karaoke

- [Poner en cola un vídeo de karaoke ya preparado](#queue-a-premade-karaoke-video)
- [Poner una canción en cola como otro usuario](#queue-a-song-as-another-user)
- [Controlar la cola a distancia](#control-queue-remotely)
- [Usar tu propia canción](#use-your-own-song)

## Poner en cola un vídeo de karaoke ya preparado { #queue-a-premade-karaoke-video }

![Poner en cola karaoke normal](../assets/images/tasks/queue-normal-karaoke.webp)

YouTube cuenta con una enorme biblioteca de vídeos de karaoke, incluidos canales como [Sing King](https://www.youtube.com/channel/UCwTRjvjVge51X-ILJ4i22ew). Para una canción popular, es probable que ya haya un vídeo de karaoke disponible. Es la forma más sencilla de empezar y **no requiere el servicio Demucs**. Sin embargo, las opciones de estilo y personalización son limitadas.

- Busca una canción. Normalmente basta con buscar por título y artista.
- También puedes pegar directamente una URL de YouTube en el cuadro de búsqueda.

!!! tip "[Búsqueda paralela en YouTube](../configuration/downloads.md#parallel-youtube-search)"
    Activa la búsqueda paralela en YouTube para buscar al mismo tiempo la consulta original y una variante de karaoke. Esto puede ayudarte a encontrar vídeos de karaoke existentes.

- La aplicación detecta automáticamente el vídeo de karaoke, por lo que no se necesita procesamiento de karaoke. Añádelo a la cola y espera a que termine la descarga.
- La canción se añade a la cola y aparece en el escenario cuando finaliza la descarga.

Si falla la descarga, consulta la [guía de solución de problemas de yt-dlp](../troubleshooting/index.md).

## Poner una canción en cola como otro usuario { #queue-a-song-as-another-user }

Normalmente los invitados usan sus propios dispositivos y solo pueden poner canciones en cola como ellos mismos. En una tableta compartida, un administrador puede iniciar sesión y poner una canción en cola como otro usuario, lo que permite añadir canciones de distintas personas desde el mismo dispositivo.

![Poner en cola como otro usuario](../assets/images/tasks/queueas.webp)

- Activa el interruptor **Queue as prompt**.
- Busca una canción como de costumbre.
- En la página previa a la cola, selecciona un usuario existente o introduce un nombre nuevo para ponerla en cola como esa persona.

## Controlar la cola a distancia { #control-queue-remotely }

No siempre es cómodo acercarse al teclado para controlar el dispositivo del escenario. Puedes usar tu propio dispositivo o el compartido para controlar la pantalla en tiempo real. Estas son las opciones disponibles:

![Control del escenario](../assets/images/queue/control.webp)

!!! note "Control de invitados y administradores"
    Los invitados pueden gestionar sus propias canciones en cola, mientras que los administradores pueden añadir canciones en nombre de otro usuario y administrar toda la cola.

    Como administrador, también puedes eliminar o reordenar canciones puestas en cola por otros usuarios.


- **Pause/Play**: pausa o reanuda la canción actual.
- **Skip**: omite la canción actual.
- **Resync**: recupera la sincronización cuando las voces y el instrumental se desajustan.
- **FF+5**: adelanta cinco segundos la canción actual.
- **Vocals**: activa o desactiva la pista de voces de apoyo (solo en canciones compatibles).
- **Vocal Volume**: ajusta el volumen de las voces (solo en canciones compatibles).
- **Style**: ajusta la [personalización](stage-and-branding.md#customize-the-stage-display) avanzada de las letras (solo en canciones compatibles).

## Usar tu propia canción { #use-your-own-song }

Si has descargado vídeos de karaoke o tienes problemas para descargar con la aplicación, puedes cargar tu propio contenido en la biblioteca.

La aplicación admite diversos formatos multimedia habituales:

- Vídeo: MP4, WEBM, MKV, MOV, AVI, M4V
- Audio: MP3, WAV, M4A, FLAC, AAC, OGG, OPUS, WEBM
- Otros: CDG (formato de karaoke heredado), ZIP (paquete de karaoke exportado por la aplicación)

<div class="grid cards" markdown>

- __Con la aplicación__

    - Abre la página Multimedia y haz clic en **Subir**.
    - Selecciona un archivo multimedia y, opcionalmente, proporciona un título y un artista.
    - Para las opciones avanzadas de procesamiento de karaoke, consulta [Crear karaoke a partir de archivos cargados](create-ai-karaoke.md).

- __Externamente__

    - Copia el archivo multimedia al directorio `MEDIA_PATH` del host.
    - Si ejecutas el servidor de forma remota, puedes usar recursos compartidos de red `SCP/SFTP` (WinSCP/FileZilla) o `SMB/NFS`.
    - Haz clic en **scan library** en la página Media para detectar el contenido nuevo.

</div>
