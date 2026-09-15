# Commencer { #getting-started }

DMKaraoke se compose de deux services.

- [Demande principale](#ways-to-deploy) : un serveur web qui fournit la file d'attente, les contrôles d'étape et la gestion des médias.
- [Services aux entreprises](demucs-service.md) : une application séparée qui exécute WhisperX et Demucs pour la séparation vocale et la génération lyrique.

Cette architecture donne aux utilisateurs la flexibilité de lancer l'application principale sur un serveur domestique léger tout en utilisant une machine plus puissante pour le service Demucs, y compris l'ordinateur d'un ami sur Internet. Les services communiquent par HTTP, permettant à un service Demucs de fournir le traitement AI pour plusieurs serveurs karaokés.

![Architecture DMKaraoke](../assets/images/architecture.webp)

La manière recommandée pour déployer l'application principale DMKaraoke est avec les conteneurs Docker sur un serveur Linux. Les installations non Docker, y compris le métal nu et LXC, ainsi que les installations Windows, sont également pris en charge.

## Moyens de déploiement { #ways-to-deploy }

L'application principale est un serveur Web FastAPI léger avec une base de données SQLite. Il peut fonctionner sur n'importe quel serveur Linux x64 ou ARM64, y compris un Raspberry Pi 4 ou un ancien ordinateur de bureau.

<div class="grid cards" markdown>

-   :material-docker: **Docker**

Recommandé pour les serveurs Linux.

[:octicons-arrow-right-24: Ouvrir le guide Docker](docker.md)

-   :material-linux: **Linux**

Exécutez l'application principale sans Docker.

[:octicons-arrow-right-24: Ouvrir le guide Linux](linux.md)

-   :material-microsoft-windows: **Windows**

Installez l'application principale ou le service Demucs sur Windows.

[:octicons-arrow-right-24: Ouvrir le guide Windows](windows.md)

</div>

### Services aux entreprises { #demucs-service }

Le service Demucs fonctionne mieux avec un GPU NVIDIA compatible CUDA. Il peut fonctionner sans un, mais le traitement sera plus lent. Vous pouvez également l'exécuter sur un autre ordinateur.

- [Service Démucs](demucs-service.md)

## Considérations relatives à la production { #production-considerations }

Sauvegardez périodiquement vos données et vos supports de l'application, et mettez à jour lorsque de nouvelles versions sont publiées.

Voir [administration du serveur](../tasks/server-administration.md) pour plus d'informations sur le déploiement de DMKaraoke dans la production, y compris des services supplémentaires tels que les serveurs proxy, les procurations inversées, la surveillance et le contrôle d'accès.
