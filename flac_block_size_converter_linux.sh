#!/usr/bin/env bash

set -euo pipefail

mkdir -p temp converted

echo
echo "====================================="
echo "FLAC Block Size Converter"
echo "Converts block size to 4608"
echo "Preserves tags"
echo "Resizes cover art to max 640x640"
echo "====================================="
echo

shopt -s nullglob

for file in *.flac; do
    echo "====================================="
    echo
    echo "Processing: $file"
    echo

    # Remove old temp files
    rm -f temp/tags.txt temp/cover.jpg temp/cover_resized.jpg

    # Export tags
    metaflac --export-tags-to=temp/tags.txt "$file"

    # Export cover art (if any)
    metaflac --export-picture-to=temp/cover.jpg "$file" 2>/dev/null || true

    # Print original block size
    blocksize=$(metaflac --list --block-number=0 "$file" |
        awk '/minimum blocksize:/ {print $3}')

    echo "Block Size     : $blocksize -> 4608"

    outfile="converted/${file%.flac}.flac"

    # Decode and encode without creating a WAV file
    flac -d -c "$file" | \
    flac -8 --blocksize=4608 -o "$outfile" -

    # Restore tags
    metaflac --import-tags-from=temp/tags.txt "$outfile"

    # Restore cover art
    if [[ -f temp/cover.jpg ]]; then

        original=$(identify -format "%wx%h" temp/cover.jpg)

        convert temp/cover.jpg \
            -resize "640x640>" \
            temp/cover_resized.jpg

        resized=$(identify -format "%wx%h" temp/cover_resized.jpg)

        echo "Original Cover : $original"
        echo "Output Cover   : $resized"

        metaflac --import-picture-from=temp/cover_resized.jpg "$outfile"
    fi

    echo
    echo "Finished: $file"
    echo
done

rm -rf temp

echo "====================================="
echo
echo "All files completed."
echo "Output folder: converted"
echo
echo "====================================="