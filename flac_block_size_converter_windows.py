import os
import re
import shutil
import subprocess


def find_flac_files(root_folder):
    flac_files = []
    for dirpath, dirnames, filenames in os.walk(root_folder):
        # Don't scan our own working folders
        dirnames[:] = [d for d in dirnames if d not in ("Converted", "temp")]
        for filename in filenames:
            if filename.lower().endswith(".flac"):
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, root_folder)
                flac_files.append((rel_path, full_path))
    return flac_files


def get_block_size(full_path):
    try:
        result = subprocess.run(
            ["metaflac", "--show-max-blocksize", full_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return f"Error: {e}"


def get_block_size_choice():
    options = {"1": "2048", "2": "4096", "3": "4608", "4": "8192"}
    default = "4608"

    print("Select FLAC block size, (Default 4608, Best for Audio players)")
    print("1) 2048")
    print("2) 4096")
    print("3) 4608")
    print("4) 8192")
    choice = input("Enter choice [1-4]: ").strip()

    return options.get(choice, default)


def get_compression_level_choice():
    options = {"1": "0", "2": "2", "3": "5", "4": "8"}
    default = "8"

    print("\nSelect FLAC compression level, (Default 8, For lowest possible size)")
    print("1) 0")
    print("2) 2")
    print("3) 5")
    print("4) 8")
    choice = input("Enter choice [1-4]: ").strip()

    return options.get(choice, default)


def clear_temp_folder(temp_folder):
    for item in os.listdir(temp_folder):
        item_path = os.path.join(temp_folder, item)
        if os.path.isfile(item_path) or os.path.islink(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)


# Labels of commands that failed for the file currently being processed
FAILED_STEPS = []


def run(cmd, label=None, silent_fail=False):
    """Run a command, return CompletedProcess (never raises).
    Prints an error message if the command fails (non-zero exit code),
    unless silent_fail=True (use for expected/benign failures)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
    except FileNotFoundError as e:
        # Tool (flac / metaflac / magick) not installed or not on PATH
        result = subprocess.CompletedProcess(cmd, 127, stdout="", stderr=str(e))

    if result.returncode != 0 and not silent_fail:
        FAILED_STEPS.append(label or cmd[0])
        tag = f" [{label}]" if label else ""
        print(f"  !! Command failed{tag} (exit code {result.returncode}): {' '.join(cmd)}")
        if result.stderr.strip():
            print(f"     stderr: {result.stderr.strip()}")
        elif result.stdout.strip():
            print(f"     stdout: {result.stdout.strip()}")
    return result


def build_tag_array(tags_path):
    """
    Reads tags.txt and returns a list of unique tag names (in order of
    first appearance). Only lines that start with NAME= count as a new tag;
    continuation lines of multi-line values (e.g. lyrics) are ignored.
    """
    tag_names = []
    if not os.path.exists(tags_path):
        return tag_names

    tag_pattern = re.compile(r'^([A-Za-z0-9_]+)=')
    seen = set()

    with open(tags_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            match = tag_pattern.match(line)
            if match:
                name = match.group(1).upper()
                if name not in seen:
                    seen.add(name)
                    tag_names.append(name)

    return tag_names


def get_tag_values(source_flac, tag_name):
    """
    Runs: metaflac --show-tag=TAGNAME source.flac
    Returns a list of values (a tag can appear more than once, and a
    value can span multiple lines, e.g. lyrics).
    """
    result = run(["metaflac", f"--show-tag={tag_name}", source_flac],
                 label=f"show tag {tag_name}")
    output = result.stdout.replace("\r\n", "\n")

    # Split the output into separate occurrences: a new occurrence starts
    # at a line beginning with TAGNAME= (case-insensitive). Any other line
    # is a continuation of the previous value.
    start_pattern = re.compile(rf'^{re.escape(tag_name)}=', re.IGNORECASE)
    values = []
    current = None

    for line in output.split("\n"):
        if start_pattern.match(line):
            if current is not None:
                values.append(current)
            current = line.split("=", 1)[1]
        elif current is not None:
            current += "\n" + line

    if current is not None:
        values.append(current)

    # Strip the trailing newline that metaflac adds after each value
    return [v.rstrip("\n") for v in values]


if __name__ == "__main__":
    # Folder where this script is located
    folder = os.path.dirname(os.path.abspath(__file__))

    # Create "Converted" and "temp" folders next to the script
    converted_folder = os.path.join(folder, "Converted")
    temp_folder = os.path.join(folder, "temp")
    os.makedirs(converted_folder, exist_ok=True)
    os.makedirs(temp_folder, exist_ok=True)

    # Get user input for block size and compression level
    block_size = get_block_size_choice()
    compression_level = get_compression_level_choice()

    print(f"\nBlock size set to: {block_size}")
    print(f"Compression level set to: {compression_level}")

    flac_list = find_flac_files(folder)

    print(f"\nScanning: {folder}")
    print(f"Found {len(flac_list)} .flac file(s):\n")

    tags_path = os.path.join(temp_folder, "tags.txt")
    cover_path = os.path.join(temp_folder, "cover.jpg")
    cover_resized_path = os.path.join(temp_folder, "cover_resized.jpg")
    wav_path = os.path.join(temp_folder, "audio.wav")

    total_files = len(flac_list)
    converted_count = 0
    skipped_count = 0
    failed_files = []  # list of (rel_path, [failed step labels])

    for rel_path, full_path in flac_list:
        print(f"=== {rel_path} ===")
        print(f"Original Block Size: {get_block_size(full_path)}")

        # 1. Clear temp folder contents
        clear_temp_folder(temp_folder)

        # 1b. Work out the destination path and skip if it already exists
        rel_subfolder = os.path.dirname(rel_path)
        dest_folder = os.path.join(converted_folder, rel_subfolder)
        filename_no_ext = os.path.splitext(os.path.basename(full_path))[0]
        dest_flac_path = os.path.join(dest_folder, filename_no_ext + ".flac")

        if os.path.exists(dest_flac_path):
            print("Skipped: already exists in Converted\n")
            skipped_count += 1
            continue

        FAILED_STEPS.clear()

        # 2. Export tags to temp/tags.txt
        run(["metaflac", f"--export-tags-to={tags_path}", full_path], label="export tags")

        # 2b. Make an array of tag names found in tags.txt
        tag_names = build_tag_array(tags_path)
        print(f"Tags found: {len(tag_names)}")

        # 3. Export cover art (if available) - missing cover is expected, not an error
        cover_result = run(
            ["metaflac", f"--export-picture-to={cover_path}", full_path],
            label="export cover", silent_fail=True
        )
        has_cover = cover_result.returncode == 0 and os.path.exists(cover_path)

        if has_cover:
            # 4. Print original resolution
            identify_result = run(["magick", "identify", "-format", "%wx%h", cover_path], label="identify cover")
            original_res = identify_result.stdout.strip()

            # 5. Resize if needed (">" only shrinks, safe to always run)
            run([
                "magick", cover_path,
                "-resize", "640x640>",
                cover_resized_path
            ], label="resize cover")

            # 6. Print resized resolution
            identify_result2 = run(["magick", "identify", "-format", "%wx%h", cover_resized_path], label="identify resized cover")
            output_res = identify_result2.stdout.strip()

            print(f"Original Cover: {original_res}")
            print(f"Output Cover  : {output_res}")
        else:
            print("No embedded cover art found.")

        # 7. Decode FLAC to WAV
        decode_result = run(["flac", "-d", "-f", full_path, "-o", wav_path], label="decode to wav")
        if decode_result.returncode != 0 or not os.path.exists(wav_path):
            if not FAILED_STEPS:
                FAILED_STEPS.append("decode to wav")
            failed_files.append((rel_path, list(FAILED_STEPS)))
            print(f"Failed: {rel_path}\n")
            continue

        # 8. Create the destination folder inside Converted
        os.makedirs(dest_folder, exist_ok=True)

        # 9. Re-encode WAV to FLAC with chosen compression/blocksize
        run([
            "flac", f"-{compression_level}",
            f"--blocksize={block_size}",
            wav_path,
            "-o", dest_flac_path
        ], label="encode flac")

        # 10. Import cover art into the new FLAC (if it existed)
        if has_cover:
            run(["metaflac", f"--import-picture-from={cover_resized_path}", dest_flac_path], label="import cover")

        # 11. Go through the tag array: fetch each tag from the ORIGINAL flac,
        #     store it in a temp variable, then set it on the NEW flac
        for tag_name in tag_names:
            if tag_name == "TIDAL_DATA":
                continue  # intentionally not copied to the new file

            values = get_tag_values(full_path, tag_name)   # temp variable(s)
            for value in values:
                run(
                    ["metaflac", f"--set-tag={tag_name}={value}", dest_flac_path],
                    label=f"set tag {tag_name}"
                )

        if FAILED_STEPS or not os.path.exists(dest_flac_path):
            # Remove the partial output so the next run retries it
            # instead of skipping it as "already exists"
            if os.path.exists(dest_flac_path):
                os.remove(dest_flac_path)
            failed_files.append((rel_path, list(FAILED_STEPS) or ["encode flac"]))
            print(f"Failed: {rel_path}\n")
        else:
            converted_count += 1
            print(f"Saved: {os.path.relpath(dest_flac_path, folder)}\n")

    # Delete the temp folder now that all files are processed
    shutil.rmtree(temp_folder, ignore_errors=True)
    print("Temp folder deleted.")

    # Summary
    print("\n===== Summary =====")
    print(f"Total FLAC files found : {total_files}")
    print(f"Converted              : {converted_count}")
    print(f"Skipped (already exist): {skipped_count}")
    print(f"Failed                 : {len(failed_files)}")
    if failed_files:
        print("\nFailed files:")
        for failed_path, steps in failed_files:
            print(f"  - {failed_path}  (failed step(s): {', '.join(steps)})")
    print()

    # Keep window open until a key is pressed
    try:
        import msvcrt
        print("Press any key to exit...")
        msvcrt.getch()
    except ImportError:
        # Not on Windows, fall back to Enter key
        input("Press Enter to exit...")
