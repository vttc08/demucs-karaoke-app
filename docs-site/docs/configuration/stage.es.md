# Escenario

![Configuración del escenario](../assets/images/settings/stage.webp){ width="400" }

Use esta sección para configurar el destino QR de la vista de escenario, los medios de espera cuando la cola está vacía y el volumen predeterminado de las voces. Estos ajustes también se pueden configurar mediante [variables de entorno](environments.md) cuando una implementación necesita valores fijos.

### URL QR del escenario { #stage-qr-url }

La URL opcional codificada en la superposición QR que se muestra en la vista de escenario. Cuando está vacía, la aplicación utiliza el nombre de host actual para crear el destino.

### URL de medios de espera del escenario { #stage-lobby-media-url }

Una URL de medio opcional usada para el bucle de espera mientras la cola está vacía. Use una URL `/media/...` con la ruta relativa a su carpeta de medios, por ejemplo `/media/stage-lobby.mp4`.

### Volumen predeterminado de las voces

El volumen de las voces que se aplica cuando se carga la página de escenario o cola tras un reinicio. Introduzca un porcentaje de `0` a `100`. El volumen de voces en directo se puede seguir cambiando desde la página de escenario mientras se ejecuta.

La variable de entorno equivalente `STAGE_VOCALS_VOLUME_DEFAULT` usa un valor decimal de `0.0` a `1.0`; por ejemplo, `0.46` representa `46%`.
