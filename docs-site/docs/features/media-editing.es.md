# Edición de medios

Las herramientas de edición de medios están disponibles para los administradores desde los controles de edición de la biblioteca multimedia.

## Recortador sin pérdida

![Recortador sin pérdida](../assets/images/videotrimmer.webp){ width="600" }

Algunas canciones de karaoke pueden tener introducciones largas, marcas o finales de recordatorio. Los vídeos musicales también pueden contener secciones sin música. Para una experiencia de karaoke óptima, usa el **Recortador sin pérdida** para eliminar estas secciones.

Cuando usas el recortador sin pérdida, los archivos auxiliares adjuntos, como las letras y las voces, se recortan automáticamente para que coincidan. El recortador usa fotogramas I (fotogramas clave) para recortar vídeo casi al instante, sin recodificarlo ni reducir su calidad.

## Editor de letras

![Editor de letras](../assets/images/subtitleeditor.webp){ width="600" }

La salida de WhisperX puede no ser perfecta, por lo que quizá quieras hacer pequeños ajustes a las letras. El **Editor de letras** convierte la salida de WhisperX en formatos estándar de subtítulos para karaoke, de modo que puedas ajustar la sincronización con un programa externo. Se admiten dos formatos: ASS y SRT.

<div class="grid cards" markdown>
- :material-subtitles:{ .lg .middle } __Formato ASS__

    ---

    ASS admite la sincronización de karaoke. Cada línea se convierte a una sincronización estándar con etiquetas `\k` y códigos de tiempo.

    Edita archivos ASS con [Aegisub](https://aegisub.org/).

- :material-subtitles-outline:{ .lg .middle } __Formato SRT__

    ---

    SRT es un formato de subtítulos muy utilizado. Cada palabra se convierte en una línea de subtítulo.

    Edita archivos SRT con [Subtitle Edit](https://www.nikse.dk/SubtitleEdit/).
</div>

## Añadir voces

![Añadir voces](../assets/images/addvocals.webp){ width="600" }

Puede resultar útil añadir voces de acompañamiento a un vídeo de karaoke ya preparado para practicar. La función **Añadir voces** te permite buscar en YouTube o subir una canción completa y, después, extraer sus voces con Demucs.

Con el complemento compatible [vocal-sync](../tasks/create-ai-karaoke.md) instalado, las voces extraídas se pueden sincronizar automáticamente con el vídeo de karaoke original. Consulta la sección **Añadir voces a un vídeo de karaoke ya preparado** para ver el flujo de trabajo completo. También puedes ajustar manualmente la sincronización de la pista vocal para añadir o reducir un retraso.
