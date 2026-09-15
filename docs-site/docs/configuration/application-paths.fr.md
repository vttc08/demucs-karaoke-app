# Chemins d'application { #application-paths }

![Paramètres des chemins d'application](../assets/images/settings/application-paths.webp){ width="400" }

Utilisez cette section pour choisir où l'application stocke les médias et les fichiers temporaires, et quels exécutables externes elle doit utiliser. Ces paramètres peuvent également être configurés avec [Variables de l'environnement](environments.md) lorsqu'un déploiement nécessite des chemins fixes.

### par le chemin du media { #media-path }

Répertoire utilisé pour les médias téléchargés, téléchargés et traités. L'application crée le répertoire en cas de besoin, et l'utilisateur en cours d'exécution doit être capable de le lire et de l'écrire.

### Chemin du cache { #cache-path }

Répertoire utilisé pour les téléchargements temporaires, le traitement des sorties, les vignettes et autres fichiers de cache. Les fichiers de cache peuvent être supprimés de la section [Outils](tools.md) lorsqu'ils ne sont plus nécessaires.

### chemin yt-dlp { #yt-dlp-path }

Le chemin ou le nom d'exécutable utilisé pour exécuter yt-dlp. L'application vérifie l'environnement virtuel actif avant de retomber sur le système `PATH`.

### Chemin Deno { #deno-path }

Le chemin Deno est configuré par défaut dans l'installation de Docker. Il est fortement recommandé d'installer Deno pour utiliser cette application afin d'éviter les problèmes de téléchargement yt-dlp.

Un chemin facultatif vers Deno pour l'exécution JavaScript externe yt-dlp. Laissez ce champ vide pour conserver le comportement par défaut de yt-dlp. Définissez-le lorsqu'une source vidéo nécessite un runtime JavaScript externe.

### Chemin FFmpeg { #ffmpeg-path }

Le chemin ou le nom d'exécutable utilisé pour exécuter FFmpeg. FFmpeg est nécessaire pour l'extraction audio, la conversion de médias et d'autres tâches de traitement.
