# Traitement des karaokés { #karaoke-processing }

Lors du traitement du karaoké, l'application principale envoie l'audio ou la vidéo complète, le cas échéant, au service Demucs pour séparation. Le service produit une piste vocale et une piste instrumentale. Les deux pistes sont renvoyées à l'application principale, où FFmpeg fusionne la piste instrumentale avec la vidéo originale et enregistre la piste vocale séparément. L'application principale utilise SSE (server-sent events) pour signaler les progrès de Demucs.

Utilisez cette page pour configurer le moteur de séparation, le format de sortie et les limites de traitement. Ces paramètres peuvent également être définis avec des [variables d’environnement](environments.md) lorsqu’un déploiement doit conserver des valeurs fixes.

![Karaoke Processing settings](../assets/images/settings/karaoke-processing.webp){ width="400" }

## Services aux entreprises { #demucs-service }

### URL du service de séparation { #separation-service-url }

L'URL du service Demucs.

### Clé API du service de séparation { #separation-service-api-key }

Une clé API optionnelle pour le service Demucs.

??? warning "API key strongly recommended for publicly exposed Demucs services"

    For users behind CG-NAT who share the Demucs service with a friend or family member, Cloudflare Tunnel or a similar service can expose Demucs to the main application. However, if the Demucs service is publicly exposed, anyone can use it, which is why an API key is strongly recommended. For setup details, see the [Demucs service environment variables](environments.md#demucs-service).

## Options de séparation { #separation-options }

### Moteur de séparation { #separation-backend }

Choisissez `Demucs` ou `Sherpa+Spleeter`.

### Modèle Demucs { #demucs-model }

The model used for separation. The default is `htdemucs`, which balances quality and speed. Other models include:

- `htdemucs`: first version of Hybrid Transformer Demucs. Trained on MusDB + 800 songs. Default model.
- `htdemucs_ft`: fine-tuned version of htdemucs, separation will take 4 times more time but might be a bit better. Same training set as htdemucs.
- `htdemucs_6s`: 6 sources version of htdemucs, with piano and guitar being added as sources. Note that the piano source is not working great at the moment.
- `hdemucs_mmi`: Hybrid Demucs v3, retrained on MusDB + 800 songs.
- `mdx`: trained only on MusDB HQ, winning model on track A at the MDX challenge.
- `mdx_extra`: trained with extra training data (including MusDB test set), ranked 2nd on the track B of the MDX challenge.
- `mdx_q`, `mdx_extra_q`: quantized version of the previous models. Smaller download and storage but quality can be slightly worse.
- `SIG`: where SIG is a single model from the model zoo.

### Modèle Sherpa+Spleeter { #sherpaspleeter-model }

The default is `fp16`. Choose `int8`, `fp16`, or `fp32`. The `int8` model is the fastest and smallest, but may have lower quality than the `fp16` and `fp32` models.

### Appareil { #device }

The device used for separation. Choose `cuda` or `cpu`, depending on the Demucs service's capabilities.

- If `cuda` is selected but the Demucs service does not support it, or uses the CPU-only Sherpa+Spleeter backend, separation falls back to the CPU.

## Options de production { #output-options }

### Format de sortie stem { #stem-output-format }

Choisissez `mp3` ou `wav`. `mp3` est recommandé pour accélérer les transferts réseau et réduire l’espace de stockage.

### Débit de la tige MP3 { #mp3-stem-bitrate }

The bitrate for MP3 stem output. The default is `320`. Set this lower, such as `128–160`, if the network connection to Demucs is slow.

### Code audio FFMPEGc { #ffmpeg-audio-codec }

The audio codec used by FFmpeg to merge the instrumental track with the original video. The default is empty, which uses stream copy. Set this only if stage clients have trouble playing the merged video. For example, iOS devices support `aac`.

## Limites de traitement { #processing-limits }

### Séparation des médias directs (MB) { #separation-direct-media-cutoff-mb }

If the media file size is below this value, the main application sends the video directly to Demucs without downloading or extracting the audio first. The default is `500`. Set this lower, such as `20–50`, if the network connection to Demucs is slow.

### Intervalle de dépouillement (secondes) { #separation-fallback-poll-interval-seconds }

Intervalle entre les demandes de progression adressées au service Demucs lorsque la connexion SSE échoue. La valeur par défaut est de `1.0` seconde.
