# Fournisseurs de lyriques personnalisés { #custom-lyrics-providers }

L'application peut charger vos propres fournisseurs de paroles fallback à l'exécution à partir de fichiers ou répertoires Python locaux.

![alt text](../assets/images/custom.webp)

## Configuration { #configuration }

Définissez `LYRICS_PROVIDER_CUSTOM_PATHS` comme une liste séparée par des virgules de dossiers ou de fichiers Python :

```bash
LYRICS_PROVIDER_CUSTOM_PATHS=/app/custom_lyrics,/mnt/shared/lyrics_provider.py
```

### Coq { #docker }

Avec Docker, montez vos fichiers de fournisseur personnalisé dans le conteneur et définissez `LYRICS_PROVIDER_CUSTOM_PATHS` avec les chemins utilisés dans le conteneur.

```yaml
      LYRICS_PROVIDER_CUSTOM_PATHS: /app/custom_lyrics
    volumes:
      - ./custom_lyrics:/app/custom_lyrics
```

## Contrat { #contract }

Utilisez l'IA pour écrire un fournisseur de paroles personnalisé (copiez ce modèle)
```
I want you to help me write a custom lyrics provider plugin based on the specifications. Please fetch this URL https://raw.githubusercontent.com/vttc08/demucs-karaoke-app/refs/heads/main/custom_lyrics_providers.md for which explains the requirements and structure of a custom lyrics provider, including the InferredSong input and the LyricsPayload output. I will include information about the lyrics provider I want to create, and you will generate the code for it. Please ensure that the generated code adheres to the requirements and structure outlined in the provided documentation.
```

Chaque module de fournisseur doit définir une seule classe de fournisseur, généralement nommée `LyricsProvider` ou `CustomLyricsProvider`.

Forme requise:

```python
from services.lyrics_types import InferredSong, LyricsPayload


class LyricsProvider:
    name = "hello-world"

    async def fetch(self, inferred_song: InferredSong, **kwargs):
        # Implement your lyrics lookup, proxy rotation, caching, etc. here. { #implement-your-lyrics-lookup-proxy-rotation-caching-etc-here }
        return LyricsPayload()
```

Exigences:

- La classe doit être constructible sans arguments.
- `name` must be a non-empty string.
- `fetch(...)` must be `async` (synchronous functions can be wrapped with `asyncio.to_thread`).
- `fetch(...)` receives the normalized song metadata as `inferred_song`.
- The loader also passes keyword hints such as `title` and `artist`, so custom implementations should accept `**kwargs` even if they do not use them.
- If a provider cannot find a match, it must return `None`. 

## Function Input (`InferredSong`) { #function-input-inferredsong }

`InferredSong` is the app's best-effort, cleaned-up song description. For lyrics lookups, the important fields are:

- `title`: the normalized song title
- `artist`: the normalized artist name, when the app could infer one
- `source`: where the metadata came from, such as YouTube or another input path


## Return Type (`LyricsPayload` or `None`) { #return-type-lyricspayload-or-none }


`LyricsPayload` is the structured return type for providers that want to be more explicit.

Il contient:

- `lyrics`: the lyrics text itself (multi-line string)
- `is_synced`: whether the lyrics have timestamps
- `provider`: a short provider name, like `hello-world`
- `inferred_song`: the `InferredSong` that was used for the lookup
- `provider_score`: confidence score used internally when the app compares multiple fallback matches
    - entre 0 et 250, où plus est mieux
- `provider_details`: optional extra metadata for debugging or future use
- `alternatives`: optional tuple of `LyricsAlternative` values when the provider
peut offrir une autre représentation du même résultat.
conserver la sécurité par défaut pour le traitement; l'interface utilisateur peut choisir une alternative TTML
et conserver le LRC de base pour la dégradation.

Exemple de fournisseur avec une mise à niveau TTML optionnelle:

```python
from services.lyrics_types import InferredSong, LyricsAlternative, LyricsPayload


class LyricsProvider:
    name = "example"

    async def fetch(self, inferred_song: InferredSong, **kwargs):
        lrc = "[00:01.00]Original synced lyrics"
        ttml = "<tt>...valid timed TTML...</tt>"
        return LyricsPayload(
            lyrics=lrc,
            is_synced=True,
            provider=self.name,
            inferred_song=inferred_song,
            alternatives=(
                LyricsAlternative(
                    lyrics=ttml,
                    format="ttml",
                    provider=self.name,
                    is_synced=True,
                ),
            ),
        )
```

Le fournisseur intégré Musixmatch utilise ce contrat pour son TTML optionnel
mise à niveau. Les défaillances de mise à niveau sont traitées comme une alternative manquante, donc la base
Le résultat des paroles reste utilisable.

## Notes de mise en œuvre { #implementation-notes }

- Use `httpx` for web requests when your provider talks to an HTTP API.
- Use `subprocess` if your provider shells out to another program.
- Un fournisseur personnalisé peut également proxy vers un serveur web dédié aux paroles.

## Exemple HelloWorld { #helloworld-example }

```python
from services.lyrics_types import InferredSong, LyricsPayload
# import other libraries such as httpx, subprocess, etc. if needed { #import-other-libraries-such-as-httpx-subprocess-etc-if-needed }

class LyricsProvider:
    name = "hello-world"

    async def fetch(self, inferred_song: InferredSong, **kwargs):
        # support both inferred_song and kwargs for title/artist hints { #support-both-inferred_song-and-kwargs-for-titleartist-hints }
        title = inferred_song.title or kwargs.get("title")
        artist = inferred_song.artist or kwargs.get("artist")
        
        # Your custom logic goes here { #your-custom-logic-goes-here }
        # lyrics = find_lyrics(title, artist) { #lyrics-find_lyricstitle-artist }
        # is_synced = check_if_synced(lyrics) { #is_synced-check_if_syncedlyrics }
        # score = calculate_provider_score(lyrics) { #score-calculate_provider_scorelyrics }

        return LyricsPayload(
            lyrics="""[00:00.00]Hello world
[00:02.00]From a custom provider
[00:04.00]This is just an example""",
            is_synced=is_synced,
            provider="hello-world",
            inferred_song=inferred_song,
            provider_score=250
        )
```

- you must import the types from `services.lyrics_types` otherwise the loader will not recognize your provider
- d'autres variables comme l'authentification, le proxy, etc. peuvent être déclarées dans le constructeur de classe ou les attributs
- `lyrics` must be a multi-line string, not a file/path/URL reference.
- `is_synced` of `False` indicate it's a plain text lyrics, while `True` indicates it has timestamps.
- do not return a `LyricsPayload` with empty lyrics; return `None` instead.
- ne retournez pas un score vide ou zéro si vous voulez que les applications considèrent votre fournisseur comme un retour; utilisez un score de 1 ou plus.
- vous pouvez utiliser la valeur la plus élevée de 250 afin que l'application préférera toujours votre fournisseur par rapport aux autres
