# Solución de problemas { #troubleshooting }

Usa esta página para encontrar problemas habituales y posibles soluciones para la aplicación y el servicio Demucs. Para instrucciones específicas de cada tarea, consulta las [guías de tareas para usuarios](../tasks/for-users.md).

## Contenido { #contents }

- [La aplicación o Demucs no están accesibles](#application-or-demucs-is-not-accessible)
    - [Falla la conexión con Demucs](#demucs-connection-fails)
- [yt-dlp no puede descargar](#yt-dlp-fails-to-download)
- [No se encuentran las letras o son incorrectas](#lyrics-cannot-be-found-or-are-incorrect)
- [La separación de voces es muy lenta](#vocal-separation-is-very-slow)
- [La alineación de WhisperX falla o tarda demasiado](#whisperx-alignment-fails-or-takes-too-long)
- [Las letras de WhisperX están mal sincronizadas](#whisperx-lyrics-are-poorly-synchronized)
- [Problemas de reproducción en iOS](#ios-playback-issues)

## La aplicación o Demucs no están accesibles { #application-or-demucs-is-not-accessible }

Si no se puede acceder a la aplicación principal, comprueba lo siguiente.

Comprueba el [ajuste HOST](../configuration/environments.md#server-and-routing). Escuchar en localhost o 127.0.0.1 hace que la aplicación solo sea accesible desde el equipo anfitrión. Para acceder desde otros dispositivos de tu red local, usa la dirección IP local del anfitrión. Al ejecutar la aplicación en Docker, escucha en 0.0.0.0 porque el contenedor utiliza una red y una capa NAT independientes.

Comprueba la asignación de puertos de Docker. En `-p 8000:8000`, el lado izquierdo es el puerto del anfitrión y el derecho es el puerto del contenedor. El puerto del anfitrión puede ser cualquier puerto libre del equipo, pero el puerto del contenedor debe coincidir con el [ajuste PORT](../configuration/environments.md#server-and-routing).

Por ejemplo, `-p 8001:8001` no funcionará si el contenedor sigue configurado con `PORT=8000`. En ese caso, usa `-p 8001:8000` o cambia el valor de `PORT` a 8001 dentro del contenedor.

Confirma también que el cortafuegos del anfitrión permite tráfico entrante en el puerto del anfitrión.

### Permitir la aplicación en el Firewall de Windows { #allow-the-application-through-windows-firewall }

En Windows, puedes crear una regla de entrada desde **Firewall de Windows Defender con seguridad avanzada**:

1. Abre **Firewall de Windows Defender con seguridad avanzada**.
2. Selecciona **Reglas de entrada** y elige **Nueva regla**.
3. Selecciona **Puerto**, elige **TCP** e introduce el puerto del anfitrión, por ejemplo 8000.
4. Selecciona **Permitir la conexión**.
5. Aplica la regla a los perfiles adecuados. **Privado** suele ser el perfil correcto para una red doméstica de confianza.
6. Pon a la regla un nombre como Karaoke Application y selecciona **Finalizar**.

??? note "También puedes crear la regla desde un terminal de PowerShell como administrador"
    ```powershell
    New-NetFirewallRule `
      -DisplayName "Karaoke Application" `
      -Direction Inbound `
      -Protocol TCP `
      -LocalPort 8000 `
      -Action Allow `
      -Profile Private
    ```

En un equipo Windows, asegúrate de que la red esté configurada como **Privada**.

??? note "Comprobar o cambiar el perfil desde un terminal de PowerShell como administrador"

    ```powershell
    Get-NetConnectionProfile |
      Where-Object { $_.NetworkCategory -ne 'Private' } |
      ForEach-Object {
        $_
        Set-NetConnectionProfile -InterfaceIndex $_.InterfaceIndex -NetworkCategory Private -Confirm:$false
      }
    ```

### Falla la conexión con Demucs { #demucs-connection-fails }

Si Demucs informa de un tiempo de espera agotado o de que no hay ruta al anfitrión, comprueba que el anfitrión y el puerto del servicio Demucs estén introducidos correctamente.

- En Docker, localhost hace referencia al contenedor actual. Usa el nombre del contenedor Demucs cuando ambos servicios estén en la misma red de Docker.
- Si Demucs se ejecuta en otro equipo de la misma red local, usa la dirección IP local de ese equipo.
- Confirma la clave de API si el servicio Demucs la requiere.
- Comprueba los registros del servicio Demucs por si contienen errores de Demucs o WhisperX.

Un inicio correcto del servicio debería incluir:

```text
INFO   Application startup complete.
```

Puedes [verificar que el servicio Demucs está operativo](../getting-started/demucs-service.md#5-verify-application-health).

En algunos casos, el entorno virtual no está activado o se usa un entorno incorrecto al iniciar el servicio Demucs. Activa el entorno virtual correcto antes de iniciarlo.

Si Demucs se ejecuta a través de Internet, consulta [Exponer un servicio Demucs remoto](../tasks/server-administration.md#expose-a-remote-demucs-service).

## yt-dlp no puede descargar { #yt-dlp-fails-to-download }

YouTube puede bloquear o limitar las direcciones IP utilizadas por proveedores de VPS. Incluso una conexión doméstica puede sufrir limitaciones o bloqueos temporales.

Si el problema es temporal, la solución más rápida es seleccionar **Reintentar** en la tarea fallida.

Si la descarga sigue fallando, [configura un servidor proxy para las descargas de yt-dlp](../tasks/server-administration.md#use-a-proxy-server-for-downloads).

Como último recurso, descarga el vídeo en tu teléfono con [Seal](https://f-droid.org/en/packages/com.junkfood.seal/) o usa yt-dlp desde otro equipo o red. Después, [sube el vídeo](../tasks/create-ai-karaoke.md#create-karaoke-from-uploaded-files) a la aplicación.

## No se encuentran las letras o son incorrectas { #lyrics-cannot-be-found-or-are-incorrect }

Asegúrate de que la aplicación principal de karaoke esté actualizada. Consulta [Actualizar](../getting-started/backup-and-restore.md#upgrade).

Para que funcionen las letras, **debes** configurar las [claves de API de Last.fm y Musixmatch](../getting-started/docker.md#3-configure-the-environment).

Actualmente, la aplicación busca en Musixmatch, LRCLIB y Netease. Si ninguno de estos proveedores contiene las letras, la aplicación no podrá encontrarlas.

La [opción de letras de Google](../tasks/create-ai-karaoke.md#3-add-lyrics) busca letras con el formato Artista - Título. Puedes copiar los resultados y pegarlos en el cuadro de texto. Las letras no tienen que estar sincronizadas; también sirven unas letras sin sincronización.

Si la aplicación encuentra letras incorrectas, es posible que Last.fm haya inferido un título o artista equivocado. Introduce el título y el artista correctos y vuelve a buscar.

Si ninguno de los proveedores integrados funciona y quieres usar tu propio proveedor, sigue las [instrucciones para proveedores de letras personalizados](../configuration/custom-lyrics-provider.md).

Si quieres, puedes abrir una solicitud de cambios para añadir tu proveedor o corregir las implementaciones actuales.

## La separación de voces es muy lenta { #vocal-separation-is-very-slow }

!!! note "El progreso de Demucs puede detenerse cerca del 90 %"

    Si Demucs parece atascado en el 90 % durante unos segundos, es normal. Demucs solo informa del progreso de la separación de voces, no de todo el trabajo de preparación y finalización, y la aplicación no puede capturar ese progreso adicional.

La separación de voces de Demucs funciona mejor con una GPU NVIDIA compatible con CUDA. Si tienes una GPU compatible con CUDA, comprueba la [salud del servicio Demucs](../getting-started/demucs-service.md#5-verify-application-health) y confirma que el backend reconoce la GPU.

Para procesar solo con CPU, [Sherpa+Spleeter](../tasks/create-ai-karaoke.md#cpu-processing) es bastante más rápido que Demucs, aunque ofrece menor calidad. Considera usarlo y revisa la [configuración del procesamiento de karaoke](../configuration/karaoke-processing.md#separation-options).

## La alineación de WhisperX falla o tarda demasiado { #whisperx-alignment-fails-or-takes-too-long }

Como WhisperX utiliza mucha VRAM, la aplicación descarga automáticamente los modelos y ejecuta la recolección de basura después de cada separación de voces. Esto aumenta ligeramente el tiempo de alineación, pero ayuda a evitar que WhisperX se bloquee.

Si WhisperX sigue bloqueándose al usar una GPU, cancela la tarea. Ejecuta [GC de Demucs](../configuration/tools.md#run-demucs-gc) para liberar memoria de la GPU y vuelve a intentarlo.

La alineación de WhisperX también puede tardar más cuando las letras son incorrectas o se detecta un idioma equivocado. Si conoces el idioma del audio, vuelve a intentarlo y [especifica el idioma manualmente](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

??? tip "Comprobar el idioma detectado en los registros"

    Consulta los registros del servicio Demucs. Cuando la alineación es incorrecta, es bastante probable que WhisperX haya detectado el idioma equivocado.

    ```text
    2026-09-13 20:34:28 - whisperx.asr - INFO -
    Detected language: ja (0.68) in first 30s of audio
    ```

Mientras WhisperX procesa una canción, puedes poner otra en cola. Una alineación normal tarda entre uno y dos minutos, menos que una canción estándar de tres minutos. También puedes preprocesar las canciones que tú o tus invitados queráis antes o después de la sesión de karaoke, cuando la velocidad de procesamiento sea menos importante.

Si un amigo tiene un equipo compatible con CUDA, pídele que ejecute el servicio Demucs; aquí están las [instrucciones para exponerlo a través de Internet](../tasks/server-administration.md#expose-a-remote-demucs-service).

## Las letras de WhisperX están mal sincronizadas { #whisperx-lyrics-are-poorly-synchronized }

Ningún modelo es perfecto, por lo que es normal que haya pequeños problemas de sincronización. En problemas importantes, el idioma detectado por WhisperX suele ser incorrecto. Si conoces el idioma del audio, vuelve a intentarlo y [especifica el idioma manualmente](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

Para instrucciones sobre cómo corregir problemas de sincronización pequeños y grandes, consulta [Volver a sincronizar letras incorrectas de WhisperX](../tasks/media-administration.md#resynchronize-inaccurate-whisperx-lyrics).

## Problemas de reproducción en iOS { #ios-playback-issues }

En dispositivos iOS puedes encontrar problemas como que el vídeo no se reproduzca, se congele, que el botón de reproducción no responda o que el vídeo vaya a tirones.

Consulta [Usar un iPhone o iPad como pantalla del escenario](../tasks/stage-and-branding.md#use-an-iphone-or-ipad-as-a-stage-display) para conocer las limitaciones y soluciones alternativas.
