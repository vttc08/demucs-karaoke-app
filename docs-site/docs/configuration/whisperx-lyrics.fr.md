# WhisperX Lyriques { #whisperx-lyrics }

![Paramètres WhisperX Lyrics](../assets/images/settings/whisperx-lyrics.webp){ width="400" }

WhisperX crée word-by-word karaoke timing à partir de textes simples ou LRC paroles. Pendant le traitement, l'application principale envoie les paroles et la piste vocale séparée au service Demucs. WhisperX détecte la langue, aligne les paroles avec la voix, et retourne un fichier JSON contenant des paroles entièrement synchronisées.

Utilisez cette page pour configurer le langage WhisperX et le workflow d'alignement. Ces paramètres peuvent également être définis avec [variables environnementales](environments.md) lorsqu'un déploiement nécessite des valeurs fixes.

### Modèle de transcription WhisperX { #whisperx-transcription-model }

Le modèle de transcription utilisé par WhisperX pour la détection des langues. La valeur par défaut est `tiny`, ce qui est recommandé parce que le moteur n'a pas besoin de transcrire l'audio complet lorsque la langue est déjà connue.

### Langue d'alignement WhisperX { #whisperx-alignment-language }

La langue utilisée par WhisperX pour l'alignement. Entrez un code de langue tel que `en` ou `zh`.

??? note "Choisir entre la détection automatique et une langue fixe"

    Activer la détection de langue pour une bibliothèque de karaoké contenant des chansons en plusieurs langues. WhisperX peut choisir le modèle d'alignement approprié, et la détection automatique est généralement plus facile pour les invités moins techniques.

    Si votre bibliothèque est principalement dans une langue, spécifiez manuellement cette langue. Ceci évite une détection inutile et la possibilité d'un résultat inexact en sélectionnant le mauvais modèle et en produisant un mauvais timing karaoké. Lorsqu'une langue est spécifiée manuellement, l'étape de transcription de détection de langue peut être ignorée.

### Détecter la langue avant la transcription { #detect-language-before-transcription }

Activer cette option pour que WhisperX détecte le langage audio avant l'alignement et sélectionner le modèle approprié.

### Utiliser des timings de paroles synchronisées { #use-synced-lyrics-timings }

Cette option est désactivée par défaut et il est recommandé de rester désactivée. WhisperX peut accepter les lignes LRC synchronisées, telles que `[0:01.000] line`, qui fournissent des horodatages individuels pour chaque ligne lyrique et peuvent améliorer la vitesse d'alignement.

Cependant, les paroles provenant de sources externes sont rarement synchronisées avec la vidéo ou l'audio utilisé pour le karaoké. L'utilisation de ces horodatages peut donc conduire à une qualité d'alignement de mot pire.

### Liste de précharges WhisperX { #whisperx-preload-list }

La liste des modèles WhisperX séparés par des virgules à télécharger et à charger à l'avance. La valeur par défaut est `transcription=tiny,align=en`. Les entrées utilisent le format `type=model`, par exemple:

- `transcription=tiny`: préchargez le modèle de transcription utilisé pour la détection des langues.
- `align=en`: préchargez le modèle d'alignement anglais.
- `align=zh`: préchargez le modèle d'alignement chinois.

Les modèles doivent être téléchargés avant de pouvoir être utilisés. Le bouton **Preload WhisperX** télécharge les modèles configurés à l'avance, avant la première tâche de traitement du karaoké.
