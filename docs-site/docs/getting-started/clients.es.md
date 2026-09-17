# Cliente de escenario

El cliente de escenario se encarga de mostrar al público las letras y el vídeo de karaoke.

Se recomiendan los **sistemas operativos de escritorio** (Windows, Linux, macOS), por ejemplo, un portátil o un ordenador de sobremesa, especialmente para mostrar el contenido en un televisor o proyector. La transmisión de pantalla desde un dispositivo móvil (AirPlay, Samsung DeX) puede funcionar, pero no se ha probado.

Los dispositivos Android son compatibles, pero pueden requerir una configuración adicional del tema del escenario para mostrarse correctamente en una ventana pequeña.

Los dispositivos iOS/iPadOS no admiten toda la funcionalidad del cliente de escenario debido a las limitaciones de Apple en los navegadores web: estos dispositivos no pueden reproducir dos flujos de audio simultáneamente. Al usar dispositivos Apple, no es posible activar las voces; solo se reproducirá el instrumental.

Además, los navegadores de algunos dispositivos Apple antiguos solo admiten medios H.264 + AAC; consulta la [guía para usar un iPhone o iPad como pantalla de escenario](../tasks/stage-and-branding.md#use-an-iphone-or-ipad-as-a-stage-display).

## Clientes invitados

Cualquier dispositivo con un navegador web moderno puede buscar, añadir a la cola y controlar contenido de karaoke.

El invitado debe poder acceder al servidor de la aplicación principal, ya sea por la red local o por Internet. Si se utiliza el aislamiento de clientes Wi-Fi (o una red de invitados), considera usar un proxy inverso y habilitar NAT loopback en el router. Consulta más información sobre la configuración de red en [administración del servidor](../tasks/server-administration.md).

Para un dispositivo compartido, una tableta o un portátil son adecuados. Considera habilitar el modo quiosco para impedir que los invitados salgan de la aplicación.

[Modo quiosco en iPad](https://support.apple.com/en-us/111795)

[Aplicación de quiosco para Android](https://github.com/RushB-fr/freekiosk)
