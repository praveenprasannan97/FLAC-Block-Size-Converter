@echo off
setlocal

:: Create folders
if not exist "temp" mkdir "temp"
if not exist "converted" mkdir "converted"

echo.
echo =====================================
echo FLAC Block Size Converter
echo Converts block size to 4608
echo Preserves tags
echo Resizes cover art to max 640x640
echo =====================================
echo.
echo Processing FLAC files...
echo.

for %%F in (*.flac) do (

    echo =====================================
    echo.
    echo Processing: %%F
    echo.

    set "NAME=%%~nF"

    :: Remove old temp files
    del /q "temp\*" >nul 2>&1

    :: Export tags
    metaflac --export-tags-to="temp\tags.txt" "%%F"

    :: Export cover art (if one exists)
    metaflac --export-picture-to="temp\cover.jpg" "%%F" >nul 2>&1

    :: Print original block size
    for /f "tokens=3" %%B in ('
        metaflac --list --block-number=0 "%%F" ^| findstr /C:"minimum blocksize:"
    ') do (
        echo Block Size     : %%B -^> 4608
    )

    :: Decode to .wav
    flac -d "%%F" -o "temp\audio.wav"

    :: Encode with new blocksize
    flac -8 --blocksize=4608 "temp\audio.wav" -o "converted\%%~nF.flac"

    :: Restore tags
    metaflac --import-tags-from="temp\tags.txt" "converted\%%~nF.flac"

    :: Restore cover art (resize if needed)
    if exist "temp\cover.jpg" (

        :: Print original resolution
        for /f "delims=" %%R in ('magick identify -format "%%wx%%h" "temp\cover.jpg"') do (
            echo Original Cover: %%R
        )

        :: Resize only if larger than 640x640
        magick "temp\cover.jpg" ^
            -resize "640x640>" ^
            "temp\cover_resized.jpg"

        :: Print resized resolution
        for /f "delims=" %%R in ('magick identify -format "%%wx%%h" "temp\cover_resized.jpg"') do (
            echo Output Cover  : %%R
        )

        metaflac --import-picture-from="temp\cover_resized.jpg" "converted\%%~nF.flac"
    )

    echo Finished: %%F
    echo.
)

:: Cleanup temp files
rmdir /s /q "temp"

echo =====================================
echo.
echo All files completed.
echo Output folder: converted
echo.
echo =====================================
echo.
pause