# Créer AI Karaoke { #create-ai-karaoke }

L'application prend en charge plusieurs façons de créer du karaoké, depuis le téléchargement d'une vidéo musicale jusqu'au traitement de vos propres fichiers. Choisissez le flux de travail qui correspond le mieux à votre matériel source et la quantité de traitement que vous souhaitez utiliser.

## Sommaire { #contents }

- [Create karaoke from a music video](#create-karaoke-from-a-music-video)
- [Create karaoke from a lyrics video](#create-karaoke-from-a-lyrics-video)
- [Create karaoke from uploaded files](#create-karaoke-from-uploaded-files)
- [Modify existing video](#modify-existing-video)
- [Add vocals to a premade karaoke video](#add-vocals-to-a-premade-karaoke-video)
- [Fastest or best-case karaoke](#fastest-or-best-case-karaoke)

## Créer du karaoké à partir d'une vidéo musicale { #create-karaoke-from-a-music-video }

La création de karaoké à partir d'une vidéo musicale offre l'expérience la plus immersive et prend en charge les styles de paroles personnalisables. C'est aussi l'option la plus exigeante en traitement.

![AI Karaoke full flow](../assets/images/tasks/ai-karaoke-fullflow.webp){ width="800" }

### 1. Sélectionnez un clip vidéo { #1-select-a-music-video }

1. Recherchez une chanson et choisissez une vidéo dans les résultats de recherche.
2. L'application n'identifie pas automatiquement si la vidéo contient des paroles ou du karaoké. Elle permet donc à la fois la séparation vocale et le traitement des paroles.

### 2. Configurer les options de karaoké { #2-configure-karaoke-options }

La page de pré-queue offre les options suivantes :

- **L'alignement des mots WhisperX** crée des paroles word-synchrones pour karaoké.
- **Rewrap lyric lines** change le nombre maximum de caractères par ligne avant de l'envelopper à la ligne suivante.
    - Pour les langues asiatiques, notamment le chinois, le japonais et le coréen (CJK), ajustez plutôt `Max CJK Chars`.
- **Language override** définit la langue utilisée pour l’[alignement WhisperX](../configuration/whisperx-lyrics.md#whisperx-alignment-language). Ce réglage désactive la détection automatique et toute langue par défaut configurée.

### 3. Ajouter des paroles { #3-add-lyrics }

WhisperX nécessite des paroles pour créer le timing karaoké. L'application recherche les fournisseurs de paroles configurés.

- Il utilise d'abord Last.fm pour déduire le titre et l'artiste du titre vidéo. Si le résultat est incorrect, entrez le titre et l'artiste manuellement avant de chercher.
- Le bouton **Google** ouvre un nouvel onglet et recherche `Artist - Title lyrics`. Copiez le résultat dans l’**éditeur de paroles**.
- Vous pouvez également importer un fichier de paroles `.lrc` ou `.txt`.
- Modifier les paroles si nécessaire avant d'ajouter la chanson à la file d'attente du karaoké.

??? tip "Upgrade LRC lyrics"

    Certaines paroles peuvent être mises à niveau en TTML (Timed Text Markup Language), généralement provenant d'Apple Music. TTML contient déjà des paroles synchronisées par mots, qui peuvent fournir un timing précis du karaoké et sauter le traitement de WhisperX.

    Si la mise à jour échoue ou renvoie les mauvaises paroles, revenez au résultat des paroles standard.

### 4. Traiter la chanson { #4-process-the-song }

Après la file d'attente, l'application télécharge la source, sépare la voix, aligne les paroles et prépare les médias karaokés pour la scène.

!!! note "En cas d’échec du traitement"

    En cas d’échec du téléchargement, consultez le [guide de dépannage de yt-dlp](../troubleshooting/index.md#yt-dlp-fails-to-download). Pour les problèmes de séparation vocale, consultez [La séparation vocale est très lente](../troubleshooting/index.md#vocal-separation-is-very-slow). Pour les problèmes d’alignement ou de synchronisation des paroles, consultez les guides de dépannage [de l’alignement WhisperX](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long) et [de la synchronisation WhisperX](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized).

## Créer karaoké à partir d'une vidéo de paroles { #create-karaoke-from-a-lyrics-video }

![Example lyrics video](../assets/images/tasks/lyricsvideo.webp)

Les vidéos Lyrics sont largement disponibles sur YouTube. Elles ne contiennent généralement pas de paroles synchronisées par mot, mais elles peuvent fournir des styles visuels et des arrière-plans que certains utilisateurs préfèrent.

### 1. Sélectionnez une vidéo de paroles { #1-select-a-lyrics-video }

1. Recherchez une chanson et choisissez une vidéo de paroles dans les résultats de recherche.
2. L'application détecte la vidéo des paroles et permet seulement la séparation vocale, en sautant le traitement des paroles.

### 2. Attendez la séparation vocale { #2-wait-for-vocal-separation }

La chanson nécessite un traitement de séparation vocale. Elle apparaît sur la scène après le traitement est terminé.

??? note "Les vidéos de paroles ne sont pas toujours bien synchronisées"

    Les vidéos Lyrics contiennent généralement des paroles synchronisées en ligne plutôt que des paroles synchronisées en mot. Elles privilégient aussi souvent les effets visuels et l'animation, de sorte que les transitions entre les lignes peuvent ne pas correspondre précisément à la musique.

!!! note "En cas d’échec du traitement"

    If downloading fails, see the [yt-dlp troubleshooting guide](../troubleshooting/index.md#yt-dlp-fails-to-download). Si la séparation vocale échoue ou prend trop de temps, consultez [La séparation vocale est très lente](../troubleshooting/index.md#vocal-separation-is-very-slow).

## Créer karaoké à partir de fichiers téléchargés { #create-karaoke-from-uploaded-files }

Créer du karaoké à partir d'un fichier MP3 téléchargé avec album art peut fournir une expérience immersive et personnalisable. Le téléchargement est également utile lorsque l'application ne peut pas télécharger une vidéo, quand un autre appareil ou réseau est mieux adapté pour télécharger, ou quand vous voulez utiliser un fichier de votre propre bibliothèque.

![Upload Autopilot](../assets/images/media/autopilot.gif)

### 1. Télécharger un fichier { #1-upload-a-file }

Cliquez sur la zone de téléchargement ou faites glisser et déposez un fichier dedans.

??? tip "Upload Autopilot"

    Autopilot prépare les options de karaoké par défaut en un seul clic :

    - Inférer les informations de suivi du nom de fichier.
    - Rechercher et télécharger des paroles.
    - Remplir le titre, l'artiste et les options de traitement du karaoké.
    - Crée des paramètres optimisés de traitement du karaoké avant la soumission.

### 2. Configurer la chanson téléchargée { #2-configure-the-uploaded-song }

Reportez-vous à [Créer un karaoké à partir d’une vidéo musicale](#create-karaoke-from-a-music-video) pour connaître les options de paroles disponibles. Les mêmes options sont proposées lors de l’importation.

### 3. Choisissez où ajouter la chanson { #3-choose-where-to-add-the-song }

Activer **Ajouter à la file d'attente** pour ajouter la chanson à la file d'attente et la montrer sur l'étape après le traitement est terminé.

!!! note "En cas d’échec du traitement"

    Si la séparation vocale échoue ou prend trop de temps, consultez [La séparation vocale est très lente](../troubleshooting/index.md#vocal-separation-is-very-slow). If lyrics alignment fails, takes too long, or produces incorrect synchronization, see [WhisperX alignment troubleshooting](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long) and [WhisperX synchronization troubleshooting](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized).

## Modifier la vidéo existante { #modify-existing-video }

L'application peut exécuter la séparation vocale et l'alignement des paroles sur les médias existants dans la bibliothèque.

![Create AI karaoke from existing media](../assets/images/media/create.gif)

### 1. Ouvrez l'éditeur de médias { #1-open-the-media-editor }

1. Ouvrez la page Médias et cliquez sur **Modifier** pour l'élément Médias.
2. Sur la page **Modifier les détails des médias**, modifier le titre, l'artiste ou les options de traitement du karaoké.
3. Utilisez **Auto** pour déduire le titre et l'artiste du nom de fichier en utilisant Last.fm.
    - Cela change le nom de la bibliothèque. Activer **Renommer sur le disque** si le nom du fichier doit également changer.

??? note "Rename on disk"

    Le fichier est rebaptisé seulement après avoir cliqué **Renommer**. Si vous voulez seulement changer le titre, l'artiste ou le nom du fichier sans traiter les médias, ne modifiez pas **AI Karaoke** ou **Lyrics Sync**.

### 2. Configurer les paroles et le traitement { #2-configure-lyrics-and-processing }

Reportez-vous à [Créer un karaoké à partir d’une vidéo musicale](#create-karaoke-from-a-music-video) pour connaître les options de paroles disponibles.

??? note "Lyrics Sync and WhisperX"

    Quand seulement **Lyrics Sync** est activé et les paroles sont fournies, l'application enregistre le fichier des paroles sans exécuter WhisperX. Editez à nouveau le média et activez **WhisperX Aligner** lorsque vous voulez créer des paroles synchronisées.

!!! note "En cas d’échec du traitement"

    Si la séparation vocale échoue ou prend trop de temps, consultez [La séparation vocale est très lente](../troubleshooting/index.md#vocal-separation-is-very-slow). If lyrics alignment fails, takes too long, or produces incorrect synchronization, see [WhisperX alignment troubleshooting](../troubleshooting/index.md#whisperx-alignment-fails-or-takes-too-long) and [WhisperX synchronization troubleshooting](../troubleshooting/index.md#whisperx-lyrics-are-poorly-synchronized).

## Ajouter du chant à une vidéo de karaoké { #add-vocals-to-a-premade-karaoke-video }

Si vous préférez les styles de paroles d'une vidéo de karaoké préfabriquée, comme celle de Sing King, mais que vous voulez des voix de soutien pour la pratique, vous pouvez utiliser l'application pour ajouter des voix à la vidéo.

??? tip "L’alignement vocal automatique nécessite vocal-sync"

    Lorsque les prérequis sont réunis, l’application peut aligner automatiquement l’instrumental du karaoké original sur l’instrumental séparé de la vidéo musicale originale. Installez l’[extra vocal-sync](../getting-started/linux.md#1-prepare-the-application-and-dependencies) ou utilisez l’[image Docker vocal-sync](../getting-started/docker.md#3-configure-the-environment) pour activer cet alignement.

### 1. Synchronisation vocale ouverte { #1-open-vocal-sync }

1. Ouvrez la page Médias et cliquez sur **Edit**.
2. Sélectionnez **Ajouter des Vocals** pour ouvrir la page Sync Vocal.

![Add vocals](../assets/images/addvocals.webp)

### 2. Préparer et aligner les voix { #2-prepare-and-align-the-vocals }

1. Recherchez YouTube ou téléchargez vos propres fichiers, puis cliquez sur **Préparer**.
2. L'application sépare la voix et l'instrumental et prépare un aperçu.
    - Lorsque `vocal-sync` est disponible, le décalage est calculé automatiquement.
3. Utilisez les boutons **+** et **-** pour régler l'offset, puis cliquez sur **Preview** pour vérifier le résultat.
    - Une valeur **+** retarde la voix. Augmentez-la si la voix commence avant l'instrument.
    - Une valeur **-** déplace la voix plus tôt. Diminuer si la voix commence après l'instrument.

??? note "Use Preview for playback"

    N'utilisez pas les commandes du lecteur multimédia pour cette vérification; elles ne jouent que la vidéo originale. Utilisez **Preview** et **Stop** plutôt.

### 3. Communiquez le résultat { #3-commit-the-result }

Cliquez sur **S'engager** lorsque l'alignement est satisfaisant.

## Le karaoké le plus rapide ou le meilleur cas { #fastest-or-best-case-karaoke }

Si vous n'avez pas de GPU compatible CUDA pour le service Demucs, vous pouvez toujours utiliser les fonctionnalités AI avec un CPU.

### Traitement CPU { #cpu-processing }

Utilisez [Sherpa+Spleeter](../configuration/karaoke-processing.md#separation-backend) pour la séparation vocale.

- Le service Demucs télécharge les modèles selon votre [configuration](../configuration/environments.md#processing-and-model-settings).
- Sherpa+Spleeter fonctionne bien sur un processeur et est significativement plus rapide que Demucs.
- La qualité de séparation n'est pas aussi bonne que Demucs.

### Mise à niveau des paroles TTML { #ttml-lyrics-upgrade }

Il n'y a pas d'alternative simple au CPU seulement à WhisperX. Une chanson typique de trois minutes peut prendre une à deux minutes pour se séparer. Cependant, certaines chansons ont une mise à jour des paroles TTML disponible.

Les timings TTML sont des timings officiels de musique-lyriques, correspondant généralement à la sortie de la chanson originale plutôt qu'à une édition vidéo particulière. Ils ne sont pas adaptés pour les vidéos de musique avec des intros, outros, ou d'autres modifications parce que les paroles peuvent devenir offset de la vidéo. Utilisez TTML pour les vidéos non musicales avec le timing de la chanson originale ou pour les fichiers MP3 téléchargés; utilisez WhisperX lorsque la vidéo comprend des sections supplémentaires ou modifiées.

Sur un appareil limité au CPU, `Sherpa+Spleeter` associé à une mise à niveau TTML offre l’expérience de karaoké la plus rapide et la meilleure qualité possible.
