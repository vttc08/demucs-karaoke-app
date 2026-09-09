# whisperx lyrics

![]i will add the screenshot later

to make word by word synced karaoke timing from standard lrc files
the main app or during the demucs process sends
the standard text or lrc files and the separated vocal traks to Demucs service.
whisperx is used to detect the language, run wav2vec model against
the lyrics and vocals track and creates .json file
containing fully synced lyrics.

make each if the configuration option ###, capitalize first word and the values in inline quote 

whisperx transcription model

default tiny. this model is only used for language detection
the backend do not need perform any audio transcription
tiny model is recommended 

whisperx alignment language

??? note detect language or not
for regular karaoke, it's recommended to enable detect language
especially your karaoke song covers many foreign languages 
it's possible to override it for individual songs
but some guest may not interaxt with advanced settings 

sometimes the whisperx language detection can be insccurate
leading to wrong model used and bad karaoke timings
if your songs are primarily single language, manually specify it.

language code e.g. en, zh which whisperx will treat the 
audio as and use the corresponding model, set this if all your karaoke songs are
same language, it will skip the transcription step.

detect language before transcription 

recommended. check this option so whisperx detect the language and use the correct model

