# Administración de contenido

Usa esta guía para gestionar el contenido importado, reparar la temporización de letras, editar archivos de vídeo y convertir formatos de karaoke CD+G.

## Contenido

- [Importar y exportar contenido](#importar-y-exportar-contenido)
- [Resincronizar letras de WhisperX imprecisas](#resynchronize-inaccurate-whisperx-lyrics)
- [Ajustar la duración y los metadatos de un vídeo](#adjust-video-duration-and-metadata)
- [Modernizar formatos CD+G](#modernizar-formatos-cdg)

## Importar y exportar contenido

Puedes descargar todos los artefactos creados por la aplicación para karaoke, incluidas las voces separadas y las letras JSON sincronizadas palabra por palabra.

1. Ve a `/media` y haz clic en **Editar**.
2. Expande **Gestión de archivos**.
3. Haz clic en **Descargar ZIP** para descargar todos los artefactos, o descarga archivos individuales.
4. Elimina archivos auxiliares, como voces y letras, cuando ya no los necesites.

La opción **Descargar ZIP** crea un archivo de los artefactos multimedia. Puedes cargarlo mediante `/upload` para restaurar el contenido de karaoke como copia de seguridad.

Para contenido gestionado externamente, la aplicación espera la siguiente convención de nombres para archivos auxiliares:

- `<song>.mp4`: el archivo de vídeo principal. Al importar un vídeo con voces separadas, debe contener únicamente el audio instrumental.
- `<song>.vocals.mp3`: el audio de las voces separadas.
- `<song>.json` o `<song>.lrc`: el archivo de letras sincronizadas palabra por palabra o estándar. Se espera que el archivo JSON haya sido generado por WhisperX.

Ejemplo de JSON de WhisperX:

```json
{"segments":[{"start":0.0,"end":5.0,"text":"Hello, world!","words":[{"start":0.0,"end":2.5,"word":"Hello"},{"start":2.5,"end":5.0,"word":"world"}]}]}
```

??? note "JSON que no es de WhisperX"

    Si el archivo JSON no se ajusta al formato de WhisperX o está mal formado, no se procesará y las letras no funcionarán.

Copia los archivos a la carpeta `media` y luego analiza la biblioteca para detectar las nuevas pistas.

## Resincronizar letras de WhisperX imprecisas { #resynchronize-inaccurate-whisperx-lyrics }

??? note "Problemas graves de sincronización"

    Si las letras avanzan rápidamente y están desincronizadas, es posible que WhisperX haya detectado el idioma incorrecto y usado un modelo de alineación equivocado. Elimina las letras JSON existentes y vuelve a ejecutar la alineación de WhisperX con una anulación de idioma especificada manualmente.

    1. En la página del editor de contenido, expande **Gestión de archivos** y elimina las letras JSON.
    2. Activa de nuevo **Sincronización de letras** y habilita **Alinear con WhisperX**.
    3. Especifica manualmente un código de idioma en **WhisperX Language Override**.

Para problemas de sincronización menores, como cuando una palabra termina demasiado pronto o permanece hasta el siguiente estribillo, puedes ajustar los tiempos con herramientas de terceros. Descarga el archivo `.vocals.mp3` como referencia de tiempo. Cuando termines de editar, carga el archivo correspondiente y el servidor lo volverá a procesar como JSON.

![Editor de subtítulos](../assets/images/subtitleeditor.webp)

### Temporización de karaoke SSA

La aplicación exporta un archivo de subtítulos `.ass` con temporización de karaoke. Puedes usar [Aegisub](https://aegisub.org/) para afinarla y exportar un archivo `.ass` nuevo.

- [Tutorial de temporización de karaoke](https://aegisub.org/docs/latest/karaoke_timing_tutorial/)
- [YouTube: Aegisub Lesson 10 - How to make a Karaoke Video](https://www.youtube.com/watch?v=4YTIaMeKXts)

![Aegisub](../assets/images/sysadmin/aegisub.gif)

1. Importa las voces y el archivo `.ass` en Aegisub.
2. Activa **Karaoke Timing** para editar la temporización de cada palabra.
3. Desactívalo para editar la temporización por líneas.
4. Haz clic con el botón izquierdo para marcar el punto de entrada y con el derecho para marcar el de salida de una línea.
5. Pulsa la barra espaciadora para previsualizar la temporización con las voces.

Esta no es una guía completa de Aegisub.

### Edición de palabras SRT

La aplicación también exporta un archivo de subtítulos `.srt` con marcadores de tiempo, donde cada palabra es una entrada de subtítulo independiente. Puedes usar [Subtitle Edit](https://www.nikse.dk/SubtitleEdit/) para afinar la temporización y exportar un archivo `.srt` nuevo.

![Subtitle Edit](../assets/images/sysadmin/subtitleedit.gif)

1. Importa las voces y el archivo `.srt` en Subtitle Edit.
2. Subtitle Edit debería generar automáticamente la forma de onda de las voces.
3. Arrastra el inicio y el final de cada palabra para modificar su temporización.

??? warning "No elimines las líneas `//wx:meta` y `//wx:time`"

    Estos marcadores de línea son necesarios para reconstruir las letras sincronizadas palabra por palabra.

### Dividir y unir líneas

![Letras largas](../assets/images/sysadmin/long-lyrics.webp)

A veces la letra original contiene líneas largas que no se dividen bien y aparecen como varias líneas en la pantalla de karaoke. Mantén un número uniforme de caracteres por línea de karaoke ajustando el diseño o redividiendo las letras.

Puedes corregirlo parcialmente [reduciendo el tamaño de texto o aumentando el ancho máximo](stage-and-branding.md#typography-and-layout).

Hay dos formas de corregir las líneas:

1. Configura **Rewrap Lyrics Lines** durante el procesamiento de WhisperX en la página [Crear karaoke con IA](create-ai-karaoke.md). El valor predeterminado es 36 caracteres por línea para inglés y 12 para CJK. Elige un límite que se adapte a tus preajustes y personalización de letras.
2. Divide y une manualmente. Divide una línea larga en la palabra donde fluya mejor, o combina varias líneas más cortas.

![Dividir y unir](../assets/images/sysadmin/merge-split.gif)

1. En el **Lyrics Editor**, elige **Split and Merge** para abrir el editor correspondiente.
2. Usa **Procesamiento automático** y especifica una **Longitud máxima de línea** para dividir automáticamente las líneas que superen el límite.
3. Haz clic en una palabra para dividir la línea después de esa palabra.
4. Haz clic en **Merge Below** para combinar la línea actual con la siguiente.
5. Deshaz cualquier cambio si es necesario.

## Ajustar la duración y los metadatos de un vídeo { #adjust-video-duration-and-metadata }

Cuando se descarga un vídeo de YouTube, conserva los metadatos predeterminados: el título es el del vídeo, el artista está vacío y el nombre de archivo es `<video_title>.mp4`. Esto puede no ser ideal para organizar la biblioteca. El vídeo también se descarga tal cual, y muchos vídeos de karaoke contienen introducciones y finales que no son adecuados para un karaoke fluido.

Consulta [Modificar un vídeo existente](create-ai-karaoke.md) para obtener información sobre cómo ajustar los metadatos de vídeo.

### Recorte sin pérdida { #lossless-trim }

??? note "El recorte sin pérdida no puede ser preciso"

    La aplicación usa fotogramas I para recortar el vídeo sin recodificarlo. Por tanto, los cortes deben producirse en un fotograma I. No es posible recortar en un punto concreto; la aplicación busca el fotograma I más cercano.

??? warning "Recorte irreversible"

    El recorte es irreversible. Una vez recortado el vídeo, se pierde el original.

![Recorte sin pérdida](../assets/images/videotrimmer.webp)

El editor muestra una línea de tiempo con todos los fotogramas I donde puede hacerse un corte.

- Arrastra los tiradores para ajustar la hora de inicio y de fin. Cada tirador se ajusta al fotograma I más cercano.
- Especifica una hora de inicio y fin en los cuadros de entrada. La aplicación elige un fotograma I que incluya cada hora indicada.
- Reproduce el vídeo y usa los botones **:material-rewind: Set** y **:material-fast-forward: Set** para fijar los puntos inicial y final.
- Usa los botones **:material-rewind:** y **:material-fast-forward:** para saltar al fotograma I anterior o siguiente.
- Usa los botones **:material-rewind: Jump** y **:material-fast-forward: Jump** para previsualizar el corte desde los puntos de entrada y salida.

??? tip "Acelera la vista previa con atajos de teclado"

    - ++i++ / ++o++ — fija los puntos de entrada y salida del recorte
    - ++bracket-left++ / ++bracket-right++ — desplázate entre los fotogramas clave detectados
    - ++comma++ / ++period++ — mueve el cabezal de reproducción un fotograma
    - ++home++ / ++end++ — desplázate al principio o al final

## Modernizar formatos CD+G

CD+G es un formato tradicional de karaoke que muestra las letras como gráficos. Se usa habitualmente con un archivo MP3 como MP3+G. La pantalla del escenario puede reproducir gráficos CD+G, pero no se admite [recortar](#lossless-trim) un archivo CD+G a menos que se convierta a vídeo.

En vez de abrir el editor de recorte sin pérdida para un archivo CD+G, la aplicación te pedirá abrir **Transcode to MP4**.

- En el editor, transcodifica los gráficos CD+G a un vídeo MP4 con el audio MP3.
- Elige **Replace the original CD+G file after the MP4 is created** para crear un elemento multimedia nuevo conservando el elemento CD+G original.
