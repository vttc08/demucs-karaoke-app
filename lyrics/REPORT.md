Implement a lyrics resolution pipeline for the karaoke app.

Goal:
Infer artist and title from messy YouTube titles and fetch synced lyrics using multiple providers.

This is a report file for AI agents to work on implementing the lyrics fetching functionality. It consists of other open source code projects and example code snippets that can be used as reference for the implementation. The main focus is parse a YouTube title, possibly in different languages, to get the artist and title of the song, then use that information to fetch the synced lyrics from Musixmatch (or alternative platforms), or unsynced lyrics. All files will be contained in the `lyrics` directory, and other projects will be referenced with a Github URL for you to fetch.

For titles, refer to the `titles` variable in `karaoke_titles.py` for a list of YouTube titles in different languages and formats that can be used for testing. 

```python
from lyrics.karaoke_titles import titles
```

## Inferring Artist and Title from YouTube Title

The popular open source project pikaraoke https://github.com/vicwomg/pikaraoke/blob/c406a10f2fd154e2d4f5c75b39f57f511f6772f3/pikaraoke/lib/metadata_parser.py has already implemented a metadata parse which uses LastFM and regex to infer the artist and title from a YouTube title. The file `metadata_parser.py` has been saved already. In addition, it also handles rate limiting and scoring the best matches. Example usage:

```python
from lyrics.metadata_parser import lookup_lastfm

print("Parsing title:", titles[0])
metadata = lookup_lastfm(titles[0])
print("Metadata:", metadata)
```

Example output:
```
Parsing title: JAY CHOU (周杰伦) - PIAO YI (飄移) INITIAL D OPENING THEME
Metadata: Jay Chou - Piao Yi
```

The results are from the LastFM API and returned as a string (which may need additional parsing), if it's not able to find a match, it will return None.

## Lyrics Fetching (New Research)

### MusixMatch (MxLRC)

https://github.com/fashni/MxLRC

Currently MxLRC is used as a CLI application, the code can be found in `mxlrc.py`. It uses the MusixMatch API to fetch synced lyrics in .lrc format. The readme can be found at https://github.com/fashni/MxLRC/blob/master/README.md, and the usage is as follows:

```
mxlrc -s "artist,title" --token YOUR_MUSIXMATCH_TOKEN
```

By default, the lyrics will be saved in `lyrics` directory. It's possible the original output from LastFM as is (no title, artist separation) may already be sufficient for finding lyrics.

```
.\mxlrc.exe -s "Sayuri & Sopholov, Fuentes Prod - Secunena" --token 

1 lyrics to fetch

[+] Searching song: Sayuri & Sopholov -  Fuentes Prod - Secunena
[+] Song found: Sayuri & Sopholov feat. Fuentes Prod - Secunena
[+] Searching lyrics: Sayuri & Sopholov feat. Fuentes Prod - Secunena
[+] Formatting lyrics
Lyrics saved: lyrics\Sayuri  Sopholov feat Fuentes Prod - Secunena.lrc
```

However, in some cases, splitting the title and artist may be necessary.

```
.\mxlrc.exe -s "張宇 - 月亮惹的禍" --token 
[X] Invalid input: 張宇 - 月亮惹的禍
[o] No valid input provided, exiting...
.\mxlrc.exe -s "張宇,月亮惹的禍" --token 

1 lyrics to fetch

[+] Searching song: 張宇 - 月亮惹的禍
[+] Song found: 張宇 - 月亮惹的禍
[+] Searching lyrics: 張宇 - 月亮惹的禍
[+] Formatting lyrics
Lyrics saved: lyrics\張宇 - 月亮惹的禍.lrc
```

In cases of lyrics failure, this is an example of the output:

```
.\mxlrc.exe -s "这一生最美的祝福,巫启贤" --token 

1 lyrics to fetch

[+] Searching song: 这一生最美的祝福 - 巫启贤
[+] Song not found.

[+] Succesfully fetch 0 out of 1 lyrics.
[o] Failed to fetch 1 lyrics.
[o] Saving list of failed items in 20260413_235503_failed.txt. You can try again using this file as the input
```

These are just CLI usage for reference, for actual implementation, the `mxlrc.py` Python API should be studied and used.

### LRCLib

Already implemented in this project.

### LyricsAPI (self-hostable)

This https://lyrics.lewdhutao.my.eu.org/documentation/lyrics consists of the full documentation of the API. The link is also a public instance of the API that can be used for testing. 

However, this only returns unsynced lyrics. Format

```json
{"data": {"artistName":, "trackName":, "trackId":, "searchEngine":, "artworkUrl":, "lyrics":"unsynced lyrics goes here"}, "metadata": {"apiVersion": "2.0"}}
```

### NetEase Music Workflow

This is one of the best option given it's vast library of Chinese lyrics. Currently this MusicBee plugin can search for NetEase Music for lyrics: https://github.com/cqjjjzr/MusicBee-NeteaseLyrics/

The project is written in C# and specific to MusicBee, but the search logic can be studied and adapted for our use case. There is a Python version (implemented by Github Copilot) in `netease_lyrics.py` with example use cases. While it works, it's still good to study the original C# code for better understanding and possible improvements.

The Python implementation can return the song ID and lyrics, which another project can be used to fetch the synced lyrics given a song ID. https://github.com/Gaohaoyang/netease-music-downloader is a NodeJS project, example usage:

```
npx netease-music-downloader lyrics 123456
```

The lyrics will be downloaded in `./downloads` folder. To implement, the code must be translated to Python by fetching the original code on Github.

## Considerations

The MusixMatch API and LastFM API both require tokens or API key, these will already be provided in `.env`, you may need to refactor the code to use the token specific to this environment. I will set the variables as follows:

```
MUSIXMATCH_TOKEN=your_musixmatch_token
LASTFM_API_KEY=your_lastfm_api_key
```

IMPORTANT: Since you'll need to refactor existing open source code, make sure to properly cite the original source and follow the license. 

## Implementation Plan

All implementations should follow objective-oriented programming and be modularized, use abstraction and interfaces where appropriate. There should be a common API that can infer lyrics, and for fetching lyrics, while child classes can implement the specific logic for each platform, since APIs can change and different platforms will become available. Lyric related tasks should not default to just one provider, but as an interface that can be implemented by different providers and use fallback logics and concurrent fetching to get the best results in addtion to robust error handling and logging.

Given the OOP nature, it's possible to have a simple interface in the CLI or a debug endpoint, since it will use the same underlying API as the production code, which will allow user to test custom inputs without needing to follow the full user flow of the karaoke app.

## Suggested Steps:
- refactor existing code of karaoke app and implement OOP friendly interfaces for title, artist parsing from YouTube title and fetching synced lyrics, add tests and debug interfaces
- implement the functions in `metadata_parser.py`, title normalizer, candidate generation and scoring logic
- convert MxLRC to a Python library and implement the fetching logic in `mxlrc.py` using the MusixMatch API, add error handling and logging
- study the code of cqjjjzr/MusicBee-NeteaseLyrics and Gaohaoyang/netease-music-downloader, implement similar logics in Python 
