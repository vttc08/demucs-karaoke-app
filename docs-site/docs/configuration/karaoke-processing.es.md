# Procesamiento de karaoke

Durante el procesamiento de karaoke, la aplicación principal envía el audio, o el vídeo completo cuando corresponde, al servicio Demucs para su separación. El servicio produce una pista vocal y una pista instrumental. Ambas pistas regresan a la aplicación principal, donde FFmpeg combina la pista instrumental con el vídeo original y guarda la pista vocal por separado. La aplicación principal usa SSE (eventos enviados por el servidor) para informar del progreso de Demucs.

Use esta página para configurar el motor de separación, el formato de salida y los límites de procesamiento. Estos ajustes también se pueden establecer mediante [variables de entorno](environments.md) cuando una implementación necesita valores fijos.

![Configuración del procesamiento de karaoke](../assets/images/settings/karaoke-processing.webp){ width="400" }

## Servicio Demucs { #demucs-service }

### URL del servicio de separación { #separation-service-url }

La URL del servicio Demucs.

### Clave de API del servicio de separación { #separation-service-api-key }

Una clave de API opcional para el servicio Demucs.

??? warning "Se recomienda encarecidamente una clave de API para servicios Demucs expuestos públicamente"

    Para usuarios detrás de CG-NAT que comparten el servicio Demucs con un amigo o familiar, Cloudflare Tunnel o un servicio similar puede exponer Demucs a la aplicación principal. Sin embargo, si el servicio Demucs se expone públicamente, cualquiera puede usarlo; por eso se recomienda encarecidamente una clave de API. Para detalles de configuración, consulte las [variables de entorno del servicio Demucs](environments.md#demucs-service).

## Opciones de separación { #separation-options }

### Backend de separación { #separation-backend }

Elija `Demucs` o `Sherpa+Spleeter`.

### Modelo Demucs

El modelo utilizado para la separación. El valor predeterminado es `htdemucs`, que equilibra calidad y velocidad. Otros modelos incluyen:

- `htdemucs`: primera versión de Hybrid Transformer Demucs. Entrenado con MusDB + 800 canciones. Modelo predeterminado.
- `htdemucs_ft`: versión ajustada de htdemucs; la separación tardará cuatro veces más, pero podría ser algo mejor. Mismo conjunto de entrenamiento que htdemucs.
- `htdemucs_6s`: versión de htdemucs con 6 fuentes, que añade piano y guitarra como fuentes. Tenga en cuenta que la fuente de piano no funciona muy bien por ahora.
- `hdemucs_mmi`: Hybrid Demucs v3, reentrenado con MusDB + 800 canciones.
- `mdx`: entrenado solo con MusDB HQ; modelo ganador de la pista A del desafío MDX.
- `mdx_extra`: entrenado con datos de entrenamiento adicionales (incluido el conjunto de pruebas de MusDB); segundo clasificado en la pista B del desafío MDX.
- `mdx_q`, `mdx_extra_q`: versiones cuantizadas de los modelos anteriores. Requieren menos descarga y almacenamiento, pero la calidad puede ser algo menor.
- `SIG`: donde SIG es un modelo individual del catálogo de modelos.

### Modelo Sherpa+Spleeter

El valor predeterminado es `fp16`. Elija `int8`, `fp16` o `fp32`. El modelo `int8` es el más rápido y pequeño, pero puede tener menor calidad que los modelos `fp16` y `fp32`.

### Dispositivo

El dispositivo usado para la separación. Elija `cuda` o `cpu`, según las capacidades del servicio Demucs.

- Si se selecciona `cuda` pero el servicio Demucs no lo admite, o usa el backend Sherpa+Spleeter solo para CPU, la separación vuelve a la CPU.

## Opciones de salida

### Formato de salida de stems

Elija `mp3` o `wav`. Se recomienda `mp3` para una transferencia de red más rápida y un almacenamiento menor.

### Tasa de bits de stems MP3

La tasa de bits para la salida de stems MP3. El valor predeterminado es `320`. Redúzcala, por ejemplo a `128–160`, si la conexión de red a Demucs es lenta.

### Códec de audio FFMPEG { #ffmpeg-audio-codec }

El códec de audio utilizado por FFmpeg para combinar la pista instrumental con el vídeo original. El valor predeterminado está vacío, lo que usa copia de flujo. Establézcalo solo si los clientes de escenario tienen problemas para reproducir el vídeo combinado. Por ejemplo, los dispositivos iOS admiten `aac`.

## Límites de procesamiento

### Límite directo de medios para la separación (MB) { #separation-direct-media-cutoff-mb }

Si el tamaño del archivo multimedia está por debajo de este valor, la aplicación principal envía el vídeo directamente a Demucs sin descargar ni extraer primero el audio. El valor predeterminado es `500`. Redúzcalo, por ejemplo a `20–50`, si la conexión de red a Demucs es lenta.

### Intervalo de sondeo alternativo de separación (segundos)

El intervalo usado para sondear el servicio Demucs en busca de actualizaciones de progreso cuando falla la conexión SSE. El valor predeterminado es `1.0` segundo.
