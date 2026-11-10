#!/bin/sh
set -eu

if [ "${YTDLP_PATH:-}" = /data/tools/yt-dlp ] && [ ! -e /data/tools/yt-dlp ]; then
    mkdir -p /data/tools
    tmp=$(mktemp /data/tools/.yt-dlp.XXXXXX)
    trap 'rm -f "$tmp"' EXIT
    cp /usr/local/share/yt-dlp "$tmp"
    chmod 755 "$tmp"
    mv -n "$tmp" /data/tools/yt-dlp
    rm -f "$tmp"
    trap - EXIT
fi

exec "$@"
