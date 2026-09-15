# Étape { #stage }

![Paramètres de l'étape](../assets/images/settings/stage.webp){ width="400" }

Utilisez cette section pour configurer la destination Stage View QR, le support de lobby de file d'attente vide et le volume vocal par défaut. Ces paramètres peuvent également être configurés avec [Variables de l'environnement](environments.md) lorsqu'un déploiement a besoin de valeurs fixes.

### URL QR de l'étape { #stage-qr-url }

L'URL facultative encodée dans la superposition QR affichée dans Stage View. Lorsque ce champ est vide, l'application utilise le nom d'hôte actuel pour créer la destination.

### URL du média Stage Lobby { #stage-lobby-media-url }

URL de média facultative utilisée pour la boucle de lobby lorsque la file d'attente est vide. Utilisez une URL `/media/...`, avec le chemin relatif vers votre dossier multimédia, tel que `/media/stage-lobby.mp4`.

### Volume vocal par défaut { #default-vocals-volume }

Le volume vocal appliqué lorsque la page Stage ou Queue se charge après un redémarrage. Entrez un pourcentage de `0` à `100`. Le volume des voix en direct peut toujours être modifié à partir de la page Stage pendant qu'elle est en cours d'exécution.

La variable d'environnement `STAGE_VOCALS_VOLUME_DEFAULT` équivalente utilise une valeur décimale de `0.0` à `1.0` ; par exemple, `0.46` représente `46%`.
