# Rutas de la aplicación

![Configuración de rutas de la aplicación](../assets/images/settings/application-paths.webp){ width="400" }

Use esta sección para elegir dónde guarda la aplicación los archivos multimedia y temporales, y qué ejecutables externos debe usar. Estos ajustes también se pueden configurar mediante [variables de entorno](environments.md) cuando la implementación necesita rutas fijas.

### Ruta de medios

El directorio usado para los medios descargados, cargados y procesados. La aplicación crea el directorio cuando es necesario, y el usuario que la ejecuta debe poder leer y escribir en él.

### Ruta de caché

El directorio usado para descargas temporales, resultados de procesamiento, miniaturas y otros archivos de caché. Los archivos de caché se pueden eliminar desde la sección [Herramientas](tools.md) cuando ya no se necesitan.

### Ruta de yt-dlp

La ruta o el nombre del ejecutable utilizado para ejecutar yt-dlp. La aplicación comprueba primero el entorno virtual activo antes de recurrir al `PATH` del sistema.

### Ruta de Deno

La ruta de Deno se configura de forma predeterminada en la instalación de Docker. Se recomienda encarecidamente instalar Deno para usar esta aplicación y evitar problemas de descarga de yt-dlp.

Una ruta opcional a Deno para la ejecución de JavaScript externo de yt-dlp. Déjela vacía para conservar el comportamiento predeterminado de yt-dlp. Configúrela cuando una fuente de vídeo requiera un entorno de ejecución JavaScript externo.

### Ruta de FFmpeg

La ruta o el nombre del ejecutable utilizado para ejecutar FFmpeg. FFmpeg es necesario para extraer audio, convertir medios y realizar otras tareas de procesamiento.
