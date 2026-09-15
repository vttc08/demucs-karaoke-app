# Page des paramètres { #settings-page }

!!! note "La page des paramètres est réservée aux administrateurs"

    Connectez-vous en tant qu’administrateur pour accéder à cette page. Créez un compte administrateur lors de la configuration initiale.

    ![Page des paramètres](../assets/images/settings.webp){ width="800" }

    Utilisez les [paramètres recommandés](#recommended-settings) comme point de départ, puis consultez les pages de chaque section pour plus de détails.

    <div class="grid cards" markdown>

    -   **Traitement karaoké**

    ---

    Configurez le moteur de séparation, le format de sortie et les limites de traitement.

    -   **Paroles WhisperX**

    ---

    Configurez la transcription, l’alignement, la synchronisation et le préchargement des modèles.

    -   **Chemins de l’application**

    ---

    Choisissez les emplacements des médias, du cache et des exécutables.

    -   **Téléchargements**

    ---

    Réglez les téléchargements yt-dlp, le proxy, la recherche parallèle et les fournisseurs de paroles.

    -   **Scène**

    ---

    Configurez les liens de la scène, la lecture du lobby et le volume vocal par défaut.

    -   **Outils**

    ---

    Vérifiez la connectivité et le stockage, mettez yt-dlp à jour ou libérez à distance la mémoire de Demucs.

    </div>

## Paramètres recommandés { #recommended-settings }

Les valeurs suivantes constituent un bon point de départ pour une expérience de karaoké fluide. Adaptez-les à votre matériel, à votre réseau et à votre manière de travailler.

### Traitement karaoké { #karaoke-processing }

- **Moteur de séparation** : `demucs`. Si Demucs n’a pas accès à un GPU, utilisez plutôt `Sherpa+Spleeter`.
- **Seuil de traitement direct des médias (Mo)** : `500`. Réduisez cette valeur, par exemple à `20–50`, si la connexion réseau vers Demucs est lente.
- **Débit des pistes MP3** : `320`. Réduisez cette valeur, par exemple à `128–160`, si la connexion réseau vers Demucs est lente.

### Paroles WhisperX { #whisperx-lyrics }

- **Détecter la langue avant l’alignement** : activé.
- **Utiliser les timings de paroles synchronisées** : désactivé.

### Téléchargements { #downloads }

- **Recherche YouTube parallèle** : activée.

### Scène { #stage }

- **URL du QR code de la scène** : configurez l’URL de votre page de file d’attente.
- **URL du média du lobby** : configurez le chemin de votre média ou de votre cache utilisé lorsque la file est vide.

Ces recommandations conviennent à de nombreuses configurations, mais vous pouvez les modifier à tout moment depuis la page des paramètres.
