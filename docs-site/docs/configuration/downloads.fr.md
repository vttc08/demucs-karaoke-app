# Téléchargements { #downloads }

![Réglages de téléchargement](../assets/images/settings/downloads.webp){ width="400" }

Utilisez cette section pour contrôler les préférences de téléchargement yt-dlp, le routage proxy, la recherche simultanée et les fournisseurs de paroles. Ces paramètres peuvent également être configurés avec [Variables de l'environnement](environments.md) lorsqu'un déploiement a besoin de valeurs fixes.

### codec vidéo yt-dlp { #yt-dlp-video-codec }

Une préférence de codec vidéo facultative pour yt-dlp. Laissez ce champ vide pour utiliser la sélection par défaut de yt-dlp.

Les navigateurs des appareils Apple ont une prise en charge limitée des codecs, définissez-la sur `avc` en cas de problèmes de lecture vidéo.

### résolution vidéo yt-dlp { #yt-dlp-video-resolution }

La résolution vidéo maximale préférée. Choisissez `Default` pour conserver le comportement actuel, ou sélectionnez `360p`, `480p`, `720p`, `1080p` ou `2160p` pour limiter les téléchargements vidéo à cette résolution ou en dessous.

### uRL du proxy yt-dlp { #yt-dlp-proxy-url }

Une URL proxy facultative pour yt-dlp et les demandes sortantes associées. Les URL proxy HTTP, HTTPS, SOCKS4 et SOCKS5 sont prises en charge. Laissez ce champ vide pour vous connecter directement.

### version yt-dlp { #yt-dlp-version }

Utilisez**Vérifier la version**pour afficher la version yt-dlp installée.**Update yt-dlp**installe la version stable, tandis que**Installer yt-dlp Nightly**installe la version nocturne. Mettez à jour yt-dlp lorsqu'un fournisseur change ou lorsque la version actuelle ne fonctionne plus avec une source vidéo.

### Recherche YouTube parallèle { #parallel-youtube-search }

Recherchez la requête d'origine et une variante de karaoké en même temps. Cela peut donner des résultats plus utiles, mais cela crée des demandes sortantes supplémentaires.

### Fournisseurs de paroles { #lyrics-providers }

Activer ou désactiver les fournisseurs de paroles intégrés :

- **NetEase lyrics**
- **LRCLIB paroles**

Désactivez un fournisseur lorsqu'il n'est pas disponible ou lorsque vous ne souhaitez pas qu'il soit utilisé lors des recherches de paroles.
