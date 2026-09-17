# Escenario y marca

Esta página explica cómo configurar el escenario para los invitados, personalizar la visualización de letras y gestionar contenido de marca y preajustes.

## Contenido

- [Configurar el escenario](#configurar-el-escenario)
- [Personalizar la pantalla del escenario](#customize-the-stage-display)
- [Marca personalizada](#marca-personalizada)
- [Preajustes de letras](#preajustes-de-letras)
- [Modificar letras desde Queue Control](#modificar-letras-desde-queue-control)
- [Usar un iPhone o iPad como pantalla de escenario](#use-an-iphone-or-ipad-as-a-stage-display)

## Configurar el escenario

### 1. Configura el código QR del escenario

Para ofrecer una experiencia fluida a los invitados, configura un código QR con una URL a la que puedan acceder sus dispositivos. Un [proxy inverso con control de acceso](server-administration.md#restringir-el-acceso-de-usuarios-de-wi-fi-para-invitados) puede ser útil cuando la cola no debe estar disponible públicamente.

![Pantalla del escenario](../assets/images/stage.webp)

1. Configura la [URL del código QR en Settings](../configuration/stage.md#stage-qr-url).
2. En la página `/stage`, pulsa ++q++ en el teclado para mostrar el código QR en la pantalla del escenario.
3. Pulsa **+** o **-** para ajustar el tamaño del código QR.

### 2. Configura la sala de espera del escenario

Cuando la cola está vacía, la aplicación muestra una sala de espera de karaoke predeterminada con un vídeo y un tono en bucle. Sustituirla por tu propio contenido puede dar un toque más personal al escenario.

![Sala de espera predeterminada](../assets/images/tasks/stage-lobby.webp)

Configura la [URL del contenido de sala de espera en Settings](../configuration/stage.md#stage-lobby-media-url).

Estas son dos formas de crear o elegir contenido para la sala de espera:

<div class="grid cards" markdown>

-   __Descargar un vídeo de YouTube__

    ---

    Sigue [Poner en cola un vídeo de karaoke ya preparado](karaoke-tasks.md#queue-a-premade-karaoke-video) para descargar un vídeo a la biblioteca.

    - Puedes [cambiar el nombre del vídeo](create-ai-karaoke.md), por ejemplo a `stage-lobby.mp4`, para localizarlo fácilmente.

-   __Crear un vídeo con Remotion__

    ---

    [Remotion](https://www.remotion.dev/) es un framework para crear vídeos mediante programación. Es compatible con asistentes de IA y más sencillo de configurar que los editores de vídeo profesionales.

</div>

## Personalizar la pantalla del escenario { #customize-the-stage-display }

La pantalla del escenario ofrece muchas opciones para personalizar las letras. Después de instalar los preajustes predeterminados, elige uno como punto de partida y ajústalo a tu local.

![Preajustes de letras](../assets/images/presets.webp)

!!! note "Las letras del escenario requieren modo de pantalla completa"

    Para evitar controles que distraigan en el escenario, las letras solo se muestran cuando el escenario está en modo de pantalla completa.

Puedes pedir a un asistente de IA que genere un archivo JSON de preajuste personalizado. Usa esta indicación como punto de partida:

??? tip "Indicación de IA para copiar y pegar"

    ```text
    Eres un diseñador creativo para una pantalla de escenario de karaoke. Genera un
    objeto JSON completo y válido para un preajuste de letras personalizado. El encargo es:

    [Describe el lugar, el ambiente, el público, los colores que quieres usar o evitar y si las
    letras serán habitualmente chinas, con alfabeto latino o una mezcla.]

    Da prioridad a la estética visual y a la legibilidad en una pantalla proyectada: elige una
    fuente, combinación de colores, peso tipográfico, espaciado, jerarquía de líneas y contorno
    coherentes, que sigan leyéndose con claridad sobre un vídeo musical en movimiento. Haz que
    el color de la letra activa se distinga visualmente sin combinaciones de bajo contraste. Usa
    una opacidad y una escala moderadas para las líneas cercanas, de modo que la línea actual se
    vea claramente desde lejos.

    Incluye el JSON con las siguientes claves y valores:
    fontPreset, customFontFamily, customFontWeight, sizeVw, lineWidthPct,
    lineGapVw, neighborLineScalePct, neighborLineOpacityPct, textColor,
    activeColor, outlineColor, outlineWidth, previousLines, nextLines,
    lineBehavior, animation, backgroundMediaEnabled, backgroundMediaPath,
    backgroundMediaOpacityPct.

    Reglas:
    - Usa uno de estos valores para fontPreset: custom, karaoke_cjk, readable_cjk, system_cjk, serif_cjk.
    - Para fuentes personalizadas, elige una familia real de Google Fonts y uno de los pesos
      admitidos: 300, 400, 500 o 700. De lo contrario, establece customFontFamily como una
      cadena vacía y customFontWeight como 700.
    - Usa únicamente colores #RRGGBB.
    - Mantén estos valores dentro de los límites: sizeVw 3.2-8.8; lineWidthPct 60-100;
      lineGapVw 0.2-2; neighborLineScalePct y neighborLineOpacityPct 30-100; outlineWidth 2-14;
      previousLines y nextLines 0-3; backgroundMediaOpacityPct 10-100.
    - Usa rolling, rolling_scroll o fixed_group para lineBehavior; usa slide, crop, fade o none
      para animation.
    - Se recomienda la animación crop para el desplazamiento clásico de karaoke.
    - No uses una imagen ni un vídeo de fondo en este diseño generado: establece
      backgroundMediaEnabled en false y backgroundMediaPath en una cadena vacía.
    - Si el usuario ha especificado un objeto JSON con backgroundMediaEnabled, conserva ese valor
      y cambia los demás valores para adaptarlos al encargo.
    ```

Para detalles técnicos adicionales, consulta [`custom_presets.md`](https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/main/custom_presets.md).

### Tipografía y diseño { #typography-and-layout }

**Typography** es la fuente usada para las letras. Puedes elegir entre cientos de fuentes mediante [Google Fonts](https://fonts.google.com/).

**Custom Font Stack** es el nombre de familia de Google Fonts que se debe cargar. El nombre distingue entre mayúsculas y minúsculas.

??? warning "Los nombres de fuente distinguen mayúsculas y minúsculas"

    `Roboto` y `roboto` se refieren a nombres de fuente diferentes. Un nombre mal escrito o con mayúsculas incorrectas no se cargará. Cargar Google Fonts también requiere conexión a Internet.

**Custom Font Weight** controla el grosor de la fuente. Las opciones disponibles incluyen Light, Regular, Medium y Bold.

![Diseño de letras](../assets/images/lyrics-layout.webp){ width="700" }

**Text Size** controla el tamaño principal del texto de letras en unidades de ancho de ventana.

**Max Width** establece el ancho máximo de una línea de letra como porcentaje del ancho del escenario.

**Line Spacing** controla el espacio entre líneas de letras visibles en unidades de ancho de ventana.

**Text Color** es el color de las letras que no están resaltadas.

**Active Color** es el color del texto o palabra de letra activa.

**Outline Color** es el color del contorno del texto que protege la legibilidad.

**Outline** controla el grosor del contorno del texto de letras.

![Líneas de letras cercanas](../assets/images/lyrics-neighbor.webp){ width="700" }

**Previous Lines** controla cuántas líneas de letras aparecen antes de la línea activa. Se ignora con `fixed_group`.

**Next Lines** controla cuántas líneas de letras aparecen después de la línea activa. Con `fixed_group`, el grupo visible contiene `1 + nextLines` señales.

**Surrounding Size** controla el tamaño de las líneas anteriores y posteriores respecto a la línea activa.

**Surrounding Opacity** controla la opacidad de las líneas anteriores y posteriores.

### Animación y comportamiento de líneas

![Animación de letras](../assets/images/tasks/lyricsanimation.gif)

**Animation** controla el efecto de transición de texto. `crop` es el más parecido al desplazamiento clásico de karaoke.

- `slide`: la palabra activa aparece más grande y vuelve a su tamaño normal durante la transición.
- `crop`: la palabra activa se revela de izquierda a derecha, como si el texto se desplazara.
- `fade`: la palabra activa aparece gradualmente cambiando su opacidad.
- `none`: la palabra nueva cambia de color sin efecto de transición.

![Comportamiento de líneas](../assets/images/tasks/lyricsbehavior.gif){ width="700" }

**Line Behavior** controla cómo avanza la ventana de letras visibles.

- `rolling` mantiene la señal activa en una ventana definida por `previousLines` y `nextLines`. La línea activa permanece en la misma posición.
- `rolling_scroll` usa la misma ventana, pero la anima hacia arriba a medida que avanzan las letras.
- `fixed_group` ignora `previousLines`, muestra un bloque fijo de `1 + nextLines` señales y avanza solo cuando la señal activa sale de ese bloque.

### Contenido de fondo

**Background Media** es la ruta relativa a la imagen o vídeo de fondo que se muestra sobre el vídeo y detrás de las letras. Consulta [Marca personalizada](#marca-personalizada).

**Background Media Enabled** controla si el contenido de fondo se muestra detrás de las letras.

**Background Opacity** controla la opacidad de la imagen o vídeo de fondo. Úsalo para atenuar un fondo brillante o una imagen oscura cuando sea necesario.

## Marca personalizada

Para karaoke con letras alineadas por WhisperX, puedes añadir una imagen o vídeo de fondo. Puede atenuar el fondo para mejorar la legibilidad de las letras, ocultar contenido sensible o añadir tu propia marca de agua o logotipo. Las imágenes transparentes, como los archivos `.png`, pueden usarse como superposiciones sobre el vídeo. Configura el fondo desde los ajustes de letras del escenario.

![Marca personalizada](../assets/images/branding.webp)

??? note "Disponible solo en el escenario"

    La fuente de fondo debe cambiarse desde la página Stage. Queue Control solo puede activar o desactivar el fondo configurado. Guarda distintas imágenes de marca en preajustes y alterna entre ellos cuando sea necesario.

Los preajustes predeterminados incluyen dos imágenes de fondo:

- `black.png`: un fondo negro liso.
- `branding1.png`: un fondo genérico con texto de marca y un logotipo a modo de demostración.

## Preajustes de letras

Toda la personalización de letras se guarda como un archivo JSON. Puedes exportarlo e importarlo, o usarlo como preajuste para compartirlo con otras personas.

En **Presets**, elige un preajuste predeterminado y haz clic en **Apply** o **Delete**. Para guardar los ajustes actuales como preajuste, haz clic en **Create** y asígnale un nombre. Usa **Update** para sobrescribir un preajuste existente.

En **Advanced Transfer**, importa o exporta los ajustes actuales como archivo JSON:

- **Download**: exporta los ajustes actuales como archivo JSON.
- **Apply**: aplica los ajustes del contenido JSON del cuadro de texto.
- **Upload**: importa un archivo JSON y reemplaza los ajustes actuales.

## Modificar letras desde Queue Control

Puedes controlar a distancia la pantalla del escenario desde Queue Control, aunque la personalización es limitada.

![Letras de Queue Control](../assets/images/queue/queuelyrics.webp)

- **Lyrics**: muestra u oculta las letras.
- **Background**: muestra u oculta la imagen o el vídeo de fondo configurado en los ajustes de Stage.
- **Target Screen**: elige qué pantalla de escenario controlar cuando hay varias conectadas.
- **Preset**: selecciona un preajuste para aplicarlo. Reemplaza los ajustes actuales.
- **Text Size** y **Max Width**: ajusta rápidamente estos dos parámetros desde Queue Control.

??? note "Aplicar frente a reemplazar"

    **Apply** solo aplica el preajuste; no cambia **Text Size** ni **Max Width**. Usa **Override** para cambiar esos ajustes además del preajuste o de los ajustes actuales.

## Usar un iPhone o iPad como pantalla de escenario { #use-an-iphone-or-ipad-as-a-stage-display }

Los dispositivos Apple pueden mostrar el escenario de karaoke, pero los navegadores de iOS y iPadOS tienen limitaciones que afectan a la reproducción.

### Limitaciones de reproducción de audio

iOS y iPadOS no pueden reproducir de forma fiable dos fuentes multimedia a la vez. Por ello, la pantalla del escenario reproduce el vídeo de karaoke o instrumental, mientras que la pista de voces se desactiva para evitar un comportamiento inestable.

- Actualmente no hay alternativa. Cuando la aplicación detecta un agente de usuario de iOS o iPadOS, las pistas vocales se desactivan.

### Compatibilidad de vídeo y audio

Las descargas de YouTube suelen usar VP9, mientras que las pistas de salida de Demucs usan MP3. Para que el procesamiento de karaoke sea eficiente, la aplicación usa copia de flujos y no modifica el contenedor MP3 al fusionar el vídeo y el audio procesado. Es posible que los dispositivos Apple no admitan vídeo VP9, audio MP3 u otros formatos.

Para mejorar la compatibilidad:

- Configura el [códec de vídeo de yt-dlp](../configuration/downloads.md#yt-dlp-video-codec) como `avc` para forzar descargas de vídeo H.264.
- Configura el [códec de audio de FFmpeg](../configuration/karaoke-processing.md#ffmpeg-audio-codec) como `aac` para recodificar el audio al fusionarlo.
- Para marca personalizada o bucles del escenario, usa contenido compatible, como vídeo H.264 con audio AAC.

Estos ajustes se aplican a canciones descargadas o procesadas nuevas. Para canciones existentes, transcodifícalas a H.264 con AAC antes de usarlas en navegadores de dispositivos Apple.
