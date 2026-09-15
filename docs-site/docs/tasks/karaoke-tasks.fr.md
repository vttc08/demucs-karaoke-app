# Tâches de Karaoké { #karaoke-tasks }

- [Queue a premade karaoke video](#queue-a-premade-karaoke-video)
- [Queue a song as another user](#queue-a-song-as-another-user)
- [Control queue remotely](#control-queue-remotely)
- [Use your own song](#use-your-own-song)

## Demander une vidéo de karaoké prémade { #queue-a-premade-karaoke-video }

![Queue normal karaoke](../assets/images/tasks/queue-normal-karaoke.webp)

YouTube propose une vaste bibliothèque de vidéos de karaoké, notamment des chaînes comme [Sing King](https://www.youtube.com/channel/UCwTRjvjVge51X-ILJ4i22ew). Pour une chanson connue, il est probable qu’une vidéo de karaoké existe déjà. C’est la manière la plus simple de commencer et elle **ne nécessite pas le service Demucs**. En revanche, les possibilités de style et de personnalisation sont limitées.

- Rechercher une chanson. La recherche par titre et par artiste est généralement suffisante.
- Vous pouvez également coller directement une URL YouTube dans la boîte de recherche.

!!! tip "[Recherche YouTube parallèle](../configuration/downloads.md#parallel-youtube-search)"
    Activer la recherche parallèle YouTube pour rechercher simultanément la requête originale et une variante karaoké. Cela peut aider à trouver des vidéos karaoké existantes.

    - L'application détecte automatiquement la vidéo de karaoké, donc aucun traitement de karaoké n'est nécessaire.
    - La chanson est ajoutée à la file d'attente et apparaît sur la scène une fois le téléchargement terminé.

    Si le téléchargement échoue, consultez le [guide de dépannage de yt-dlp](../troubleshooting/index.md).

## Queue une chanson comme un autre utilisateur { #queue-a-song-as-another-user }

Normalement, les clients utilisent leurs propres appareils pour faire la file d'attente et peuvent seulement faire la file d'attente comme eux-mêmes. Sur une tablette partagée, un administrateur peut se connecter et faire la file d'attente comme un autre utilisateur, ce qui permet aux chansons de différents utilisateurs d'être en file d'attente sur le même appareil.

![Queue as another user](../assets/images/tasks/queueas.webp)

- Activer le **Queue en tant qu'invite**.
- Cherchez une chanson normalement.
- Sur la page de pré-queue, sélectionnez un utilisateur existant ou entrez un nouveau nom dans la file d'attente.

## Contrôle à distance de la file d'attente { #control-queue-remotely }

Il peut ne pas être pratique pour le clavier de contrôler l'appareil de scène. Vous pouvez utiliser votre propre appareil ou l'appareil partagé pour contrôler l'écran en temps réel.

![Stage control](../assets/images/queue/control.webp)

!!! note "Guest and admin control"
    Les clients peuvent gérer leurs propres chansons en file d'attente, tandis que les administrateurs peuvent faire la queue au nom d'un autre utilisateur et gérer la file d'attente complète.

    En tant qu'administrateur, vous pouvez également supprimer ou réarranger les chansons en attente par d'autres utilisateurs.


    - **Pause/Play**: Pause ou reprend la chanson actuelle.
    - **Skip**: Sautez la chanson actuelle.
    - **Resync**: Récupérer de la désynchronisation vocale et instrumentale.
    - **FF+5**: Faites avancer la chanson actuelle de 5 secondes.
    - **Vocals**: Toggle la piste de support vocal en marche ou en panne (chants supportés uniquement).
    - ** Volume vocal** : Ajustez le volume vocal (chants pris en charge uniquement).
    - **Style**: Adjust advanced lyrics [customization](stage-and-branding.md#customize-the-stage-display) (supported songs only).

## Utilisez votre propre chanson { #use-your-own-song }

Si vous avez téléchargé des vidéos de karaoké ou avez des difficultés à télécharger en utilisant l'application, vous pouvez télécharger votre propre média dans la bibliothèque.

L'application prend en charge une variété de formats de médias couramment utilisés :

- Vidéo: MP4, WEBM, MKV, MOV, AVI, M4V
- Audio: MP3, WAV, M4A, FLAC, AAC, OGG, OPUS, WEBM
- Autre: CDG (format de karaoké légiférant), ZIP (paquet de karaoké exporté de l'application)

<div class="grid cards" markdown>

-  Utilisation de l'application  

    - Ouvrez la page Médias et cliquez sur **Télécharger**.
    - Sélectionnez un fichier multimédia et éventuellement fournir un titre et un artiste.
    - For advanced karaoke processing options, refer to the [Create karaoke from uploaded files](create-ai-karaoke.md).

-  Externalement  

    - Copy the media file to the `MEDIA_PATH` directory on the host.
    - If running the server remotely, you can use `SCP/SFTP` (WinSCP/FileZilla), `SMB/NFS` network shares
    - Cliquez sur **scan library** dans la page Médias pour détecter les nouveaux médias.

</div>
