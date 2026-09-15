# Étape & Branding { #stage-branding }

Cette page explique comment configurer la scène pour les invités, personnaliser l'affichage des paroles, gérer les médias de marque et les préréglages.

## Sommaire { #contents }

- [Configure the stage](#configure-the-stage)
- [Customize the stage display](#customize-the-stage-display)
- [Custom branding](#custom-branding)
- [Lyric presets](#lyric-presets)
- [Modify lyrics from Queue Control](#modify-lyrics-from-queue-control)
- [Use an iPhone or iPad as a stage display](#use-an-iphone-or-ipad-as-a-stage-display)

## Configurer l'étape { #configure-the-stage }

### 1. Configurer le code QR de l'étape { #1-configure-the-stage-qr-code }

To provide a seamless experience for guests, configure a QR code with a URL that their devices can access. A [reverse proxy with access control](server-administration.md#restrict-access-to-guest-wi-fi-users) can be useful when the queue should not be publicly available.

![Stage display](../assets/images/stage.webp)

1. Configure the [QR code URL in Settings](../configuration/stage.md#stage-qr-url).
2. On the `/stage` page, press ++q++ on the keyboard to display the QR code on the stage screen.
3. Appuyez sur **+** ou **-** pour ajuster la taille du code QR.

### 2. Configurer le lobby de la scène { #2-configure-the-stage-lobby }

Lorsque la file d'attente est vide, l'application affiche un lobby par défaut de karaoké avec une vidéo en boucle et un ton.

![Default lobby](../assets/images/tasks/stage-lobby.webp)

Configurez l’[URL du média du lobby de scène dans les paramètres](../configuration/stage.md#stage-lobby-media-url).

Voici deux façons de créer ou de choisir les médias de lobbying :

<div class="grid cards" markdown>

-    Télécharger une vidéo de YouTube  

    ---

    Follow [Queue a premade karaoke video](karaoke-tasks.md#queue-a-premade-karaoke-video) to download a video to the library.

    - You can [rename the video](create-ai-karaoke.md), for example to `stage-lobby.mp4`, for easy reference.

-    Créer une vidéo avec Remotion  

    ---

    [Remotion](https://www.remotion.dev/) is a framework for creating videos programmatically. It is AI-agent-friendly and easy to set up compared with professional video editors.

</div>

## Personnaliser l'affichage de la scène { #customize-the-stage-display }

Après avoir installé les préréglages par défaut, choisissez-en un comme point de départ et ajustez-le pour correspondre à votre lieu.

![Lyrics presets](../assets/images/presets.webp)

!!! note "Stage lyrics require fullscreen mode"

    Pour éviter les contrôles distrayants sur la scène, les paroles ne sont affichées que lorsque la scène est en mode plein écran.

    Vous pouvez demander à un assistant AI de générer un fichier JSON préréglé personnalisé. Utilisez l'invite suivante comme point de départ:

??? tip "Copy-and-paste AI prompt"

    ```text
    You are a creative designer for a karaoke stage display. Generate one complete,
    valid JSON object for a custom lyrics preset. The design brief is:

    [Describe the venue, mood, audience, colors to use or avoid, and whether the
    lyrics will often be Chinese, Latin-script, or mixed.]

    Prioritize visual aesthetics and projected-screen legibility: choose a cohesive
    font, color scheme, typography weight, spacing, line hierarchy, and outline
    that still read clearly over a moving music video. Make the active lyric color
    visually distinct without using low-contrast combinations. Use restrained
    neighbor-line opacity and scale so the current line is obvious from a distance.

    Include the JSON with the following keys and values:
    fontPreset, customFontFamily, customFontWeight, sizeVw, lineWidthPct,
    lineGapVw, neighborLineScalePct, neighborLineOpacityPct, textColor,
    activeColor, outlineColor, outlineWidth, previousLines, nextLines,
    lineBehavior, animation, backgroundMediaEnabled, backgroundMediaPath,
    backgroundMediaOpacityPct.

    Rules:
    - Use one of fontPreset: custom, karaoke_cjk, readable_cjk, system_cjk, serif_cjk.
    - For custom fonts, choose a real Google Fonts family and one supported
      weight from 300, 400, 500, or 700. Otherwise set customFontFamily to an empty
      string and customFontWeight to 700.
    - Use #RRGGBB colors only.
    - Keep values within: sizeVw 3.2-8.8; lineWidthPct 60-100; lineGapVw 0.2-2;
      neighborLineScalePct and neighborLineOpacityPct 30-100; outlineWidth 2-14;
      previousLines and nextLines 0-3; backgroundMediaOpacityPct 10-100.
    - Use rolling, rolling_scroll, or fixed_group for lineBehavior; use slide,
      crop, fade, or none for animation.
    - The crop animation is preferred for classic karaoke scrolling.
    - Do not use a background image or video in this generated design: set
      backgroundMediaEnabled to false and backgroundMediaPath to an empty string.
    - If the user has specified a JSON object with backgroundMediaEnabled, keep
      that value and change the other values to match the design brief.
    ```

    For additional technical details, refer to [`custom_presets.md`](https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/main/custom_presets.md).

### Typographie et mise en page { #typography-and-layout }

**Typography** is the font used for lyrics. You can choose from hundreds of fonts through [Google Fonts](https://fonts.google.com/).

**Custom Font Stack** est le nom de famille des polices Google à charger. Le nom de police est sensible à la casse.

??? warning "Font names are case-sensitive"

    `Roboto` and `roboto` refer to different font names. A misspelled or incorrectly cased name will not load. Loading Google Fonts also requires an internet connection.

    **Custom Font Weight** contrôle l'épaisseur de la police. Les choix disponibles incluent Light, Regular, Medium et Bold.

    ![Lyrics layout](../assets/images/lyrics-layout.webp){ width="700" }

    **Taille du texte** contrôle la taille principale du texte lyrique dans les unités viewport-width.

    **Max Largeur** fixe la largeur maximale de la ligne lyrique en pourcentage de la largeur de la scène.

    **Ligne Spacing** contrôle l'espace entre les lignes lyriques visibles dans les unités de la largeur du port de vue.

    ** Couleur du texte** est la couleur des paroles qui ne sont pas actuellement surlignées.

    ** Couleur active** est la couleur du texte lyrique actif ou mot actif.

    **Couleur hors ligne** est la couleur du contour du texte qui protège la lisibilité.

    **Outline** contrôle la largeur du texte lyrique.

    ![Neighboring lyric lines](../assets/images/lyrics-neighbor.webp){ width="700" }

    **Previous Lines** controls how many lyric lines appear before the active line. This is ignored by `fixed_group`.

    **Next Lines** controls how many lyric lines appear after the active line. With `fixed_group`, the visible group contains `1 + nextLines` cues.

    **La taille d'arrondi** contrôle la taille des lignes précédentes et suivantes par rapport à la ligne active.

    **L'opacité d'arrondi** contrôle l'opacité des lignes précédentes et suivantes.

### Animation et comportement en ligne { #animation-and-line-behavior }

![Lyrics animation](../assets/images/tasks/lyricsanimation.gif)

**Animation** controls the text transition effect. `crop` is closest to the classic karaoke scrolling effect.

- `slide`: The active word pops out larger and returns to its normal size as it transitions.
- `crop`: The active word is revealed from left to right, as if the text is scrolling.
- `fade`: The active word fades in by changing its opacity.
- `none`: The new word changes color without a transition effect.

![Line behavior](../assets/images/tasks/lyricsbehavior.gif){ width="700" }

**Line Behavior** contrôle l'évolution de la fenêtre lyrique visible.

- `rolling` keeps the active cue in a window defined by `previousLines` and `nextLines`. The active line remains in the same position.
- `rolling_scroll` uses the same window but animates it upward as the lyrics advance.
- `fixed_group` ignores `previousLines`, shows a fixed chunk of `1 + nextLines` cues, and advances only after the active cue leaves that chunk.

### Médias généraux { #background-media }

**Background Media** is the relative path to the background image or video shown over the video and behind the lyrics. See [Custom branding](#custom-branding).

**Le support de fond Activé** contrôle si le support de fond est affiché derrière les paroles.

**Opacité de fond** contrôle l'opacité de l'image ou de la vidéo de fond. Utilisez-la pour réduire un fond lumineux ou une image sombre au besoin.

## Marque personnalisée { #custom-branding }

For karaoke with WhisperX-aligned lyrics, you can add a background image or video. This can dim the background to improve lyric readability, block sensitive content, or add your own watermark or logo. Transparent images such as `.png` files can be used as overlays on top of the video. Configure the background from the stage lyrics settings.

![Custom branding](../assets/images/branding.webp)

??? note "Only available on the stage"

    La source d'arrière-plan doit être modifiée depuis la page Stage. Queue Control ne peut que activer ou désactiver l'arrière-plan configuré. Enregistrer différentes images de marque pour prérégler et basculer entre les préréglages lorsque nécessaire.

    Les préréglages par défaut comprennent deux images de fond :

    - `black.png`: A plain black background.
    - `branding1.png`: A generic background with branding text and a logo for demonstration purposes.

## Préréglages lyriques { #lyric-presets }

Toute personnalisation lyrique est enregistrée comme un fichier JSON. Vous pouvez exporter et importer le fichier, ou l'utiliser comme un préréglage à partager avec d'autres.

Sous **Presets**, choisissez un préréglage par défaut et cliquez sur **Appliquer** ou **Supprimer**. Pour enregistrer les paramètres actuels comme préréglage, cliquez sur **Créer** et donnez-lui un nom. Utilisez **Update** pour écraser un préréglage existant.

Sous **Transfert avancé**, importez ou exportez les paramètres actuels comme fichier JSON :

- **Télécharger** : Exportez les paramètres actuels en tant que fichier JSON.
- **Appliquer** : Appliquer les paramètres du contenu JSON dans la zone de texte.
- **Upload** : Importez un fichier JSON et remplacez les paramètres actuels.

## Modifier les paroles de Queue Control { #modify-lyrics-from-queue-control }

Vous pouvez contrôler à distance l'affichage d'étape depuis Queue Control, bien que la personnalisation soit limitée.

![Queue Control lyrics](../assets/images/queue/queuelyrics.webp)

- **Lyriques**: Montrez ou cachez les paroles.
- **Contexte** : Afficher ou masquer l'image ou la vidéo de fond configurée dans les paramètres de la scène.
- **Écran cible** : Choisissez l'écran de scène à contrôler lorsque plusieurs écrans sont connectés.
- **Preset**: Sélectionnez un preset à appliquer. Ceci remplace les paramètres actuels.
- **Taille du texte** et **Max Largeur**: Réglez rapidement ces deux paramètres à partir de Queue Control.

??? note "Apply versus Override"

    **Appliquer** n'applique que le préréglage; il ne change pas **Taille du texte** ou **Max Largeur**. Utilisez **Override** pour modifier ces paramètres au-dessus du préréglage ou des paramètres actuels.

## Utiliser un iPhone ou un iPad comme écran de scène { #use-an-iphone-or-ipad-as-a-stage-display }

Les appareils Apple peuvent afficher le stade karaoké, mais les navigateurs iOS et iPadOS ont des limites qui affectent la lecture.

### Limites de lecture audio { #audio-playback-limitations }

iOS et iPadOS ne peuvent pas jouer deux sources multimédias de manière fiable en même temps. L'écran de scène joue donc la vidéo karaoké ou instrumental, tandis que la piste vocale est désactivée pour éviter un comportement instable.

- Aucune solution de rechange n'est actuellement disponible. Lorsque l'application détecte un agent utilisateur iOS ou iPadOS, les pistes vocales sont désactivées.

### Compatibilité vidéo et audio { #video-and-audio-compatibility }

Les téléchargements YouTube sont typiquement VP9, tandis que les pistes de sortie Demucs utilisent MP3. Pour un traitement efficace du karaoké, l'application utilise la copie de flux et ne modifie pas le conteneur MP3 lors de la fusion de la vidéo et du son traité.

Pour une meilleure compatibilité:

- Set [yt-dlp video codec](../configuration/downloads.md#yt-dlp-video-codec) to `avc` to force H.264 video downloads.
- Set [FFmpeg audio codec](../configuration/karaoke-processing.md#ffmpeg-audio-codec) to `aac` to re-encode the audio when merging.
- Pour le branding personnalisé ou les boucles de scène, utilisez des supports compatibles tels que la vidéo H.264 avec audio AAC.

Ces paramètres s'appliquent aux chansons nouvellement téléchargées ou traitées. Pour les chansons existantes, transcodez-les à H.264 avec AAC avant de les utiliser sur les navigateurs de périphériques Apple.
