# Herramientas

![Configuración de herramientas](../assets/images/settings/tools.webp){ width="400" }

Use esta sección para inspeccionar el estado de red y almacenamiento sin cambiar la configuración principal de la aplicación. Estas acciones solo están disponibles para administradores.

### Información del proxy

Seleccione **Comprobar proxy** para inspeccionar la conexión saliente actual mediante `ipinfo.io/json`. El resultado muestra la dirección IP, ubicación y organización detectadas, lo que puede ayudar a confirmar si se está utilizando un proxy configurado.

### Uso de almacenamiento

Seleccione **Comprobar almacenamiento** para estimar el espacio utilizado por los medios, archivos de caché y la base de datos SQLite. El resultado también muestra el total combinado.

### Limpiar caché y base de datos

Seleccione **Limpiar caché y BD** para eliminar archivos temporales de caché y filas obsoletas de la base de datos. Esto no elimina los archivos multimedia de la ruta de medios configurada, pero revise el resultado antes de confiar en un elemento que pueda haberse informado como ausente.

### Comprobar Demucs { #check-demucs }

Úselo para comprobar la conectividad con el servicio Demucs después de añadir o modificar la URL o la clave de API de Demucs.

### Ejecutar GC de Demucs { #run-demucs-gc }

Fuerza manualmente una limpieza mediante recolección de basura en el servicio Demucs, descargando todos los modelos de Demucs y WhisperX para liberar VRAM.
