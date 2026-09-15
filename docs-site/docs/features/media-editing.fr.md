# Édition des médias { #media-editing }

Les outils d'édition multimédia sont disponibles pour les administrateurs à partir des contrôles d'édition de la médiathèque.

## Trimmer sans perte { #lossless-trimmer }

![Trimmer sans perte](../assets/images/videotrimmer.webp){ width="600" }

Certaines chansons de karaoké peuvent avoir de longues intros, branding, ou rappel outros. Les vidéos musicales peuvent également contenir des sections sans musique. Pour la meilleure expérience de karaoké, utilisez le **Lossless Trimmer** pour supprimer ces sections.

Lorsque vous utilisez le pare-chocs sans perte, les sidecars attachés tels que les paroles et les chants sont automatiquement pare-chocs. Le pare-chocs utilise des i-frames (keyframes) pour découper la vidéo presque instantanément sans réencodage ni réduction de qualité.

## Éditeur de textes { #lyrics-editor }

![Éditeur de textes](../assets/images/subtitleeditor.webp){ width="600" }

La sortie WhisperX n'est peut-être pas parfaite, et vous voudrez peut-être apporter des ajustements mineurs aux paroles. Le **Lyrics Editor** convertit la sortie WhisperX en sous-titres karaoké standard pour que vous puissiez ajuster le timing avec un programme externe.

<div class="grid cards" markdown>
- :material-subtitles:{ .lg .middle } __Format ASS__

    ---

ASS prend en charge le timing karaoké. Chaque ligne est convertie en timing standard avec les balises `\k` et les codes horaires.

Modifier les fichiers ASS avec [Aegisub](https://aegisub.org/).

- :material-subtitles-outline:{ .lg .middle } __Format SRT__

    ---

SRT est un format de sous-titre largement utilisé. Chaque mot est converti en ligne de sous-titre.

Modifier les fichiers SRT avec [Modifier le sous-titre](https://www.nikse.dk/SubtitleEdit/).
</div>

## Ajouter des vocabulaires { #add-vocals }

![Ajouter des vocabulaires](../assets/images/addvocals.webp){ width="600" }

Il peut être utile d'ajouter des voix de soutien à une vidéo de karaoké pré-made pour la pratique. La fonction **Add Vocals** vous permet de rechercher YouTube ou de télécharger une chanson complète, puis extraire ses voix avec Demucs.

Avec le [vocal-sync supplémentaire](../tasks/create-ai-karaoke.md) installé, les voix extraites peuvent être synchronisées automatiquement avec la vidéo originale du karaoké. Voir le **Ajouter des voix à une vidéo pré-made du karaoké** pour le workflow complet. Vous pouvez également ajuster manuellement le timing de la piste vocale pour ajouter ou soustraire un délai.
