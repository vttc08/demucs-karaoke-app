# Primeros pasos

DMKaraoke consta de dos servicios.

- [Aplicación principal](#ways-to-deploy): un servidor web que proporciona la cola, los controles del escenario y la gestión de medios.
- [Servicio Demucs](demucs-service.md): una aplicación independiente que ejecuta WhisperX y Demucs para separar voces y generar letras.

Esta arquitectura permite ejecutar la aplicación principal en un servidor doméstico ligero y usar una máquina más potente para el servicio Demucs, incluso el equipo de un amigo a través de Internet. Los servicios se comunican mediante HTTP, por lo que un único servicio Demucs puede proporcionar procesamiento con IA a varios servidores de karaoke.

![Arquitectura de DMKaraoke](../assets/images/architecture.webp)

La forma recomendada de desplegar la aplicación principal de DMKaraoke es mediante contenedores Docker en un servidor Linux. También se admiten instalaciones sin Docker, incluidas las instalaciones bare-metal y LXC, así como las instalaciones de Windows.

## Formas de despliegue { #ways-to-deploy }

La aplicación principal es un servidor web ligero de FastAPI con una base de datos SQLite. Puede ejecutarse en cualquier servidor Linux x64 o ARM64, incluidos una Raspberry Pi 4 o un ordenador de oficina antiguo.

<div class="grid cards" markdown>

-   :material-docker: **Docker**

    Recomendado para servidores Linux.

    [:octicons-arrow-right-24: Abrir la guía de Docker](docker.md)

-   :material-linux: **Linux**

    Ejecuta la aplicación principal sin Docker.

    [:octicons-arrow-right-24: Abrir la guía de Linux](linux.md)

-   :material-microsoft-windows: **Windows**

    Instala la aplicación principal o el servicio Demucs en Windows.

    [:octicons-arrow-right-24: Abrir la guía de Windows](windows.md)

</div>

### Servicio Demucs

El servicio Demucs funciona mejor con una GPU NVIDIA compatible con CUDA. Puede ejecutarse sin ella, pero el procesamiento será más lento. También puedes ejecutarlo en otro ordenador.

- [Servicio Demucs](demucs-service.md)

## Consideraciones de producción

Haz copias de seguridad periódicas de los datos y los medios de la aplicación, y actualiza cuando se publiquen nuevas versiones. Consulta [Copia de seguridad, restauración y actualización](backup-and-restore.md) para obtener más información.

Consulta [administración del servidor](../tasks/server-administration.md) para obtener más información sobre el despliegue de DMKaraoke en producción, incluidos servicios adicionales como servidores proxy, proxies inversos, monitorización y control de acceso.
