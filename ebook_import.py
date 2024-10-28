import os
import time
import subprocess
import re
import shutil
import zipfile
from lxml import etree

INPUT_DIR = "/mnt/input"
OUTPUT_DIR = "/mnt/output"
LIBRARY_DIR = "/mnt/library"
CALIBREDB = "/opt/calibre/calibredb"
FETCH_BOOK_METADATA = "/opt/calibre/fetch-ebook-metadata"

def ensure_directories_exist():
    directories = [
        f"{OUTPUT_DIR}/failed",
        f"{OUTPUT_DIR}/skipped",
        f"{OUTPUT_DIR}/imported"
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    print("Ensured all necessary directories exist.")

def epub_info(fname):
    def xpath(element, path):
        return element.xpath(
            path,
            namespaces={
                "n": "urn:oasis:names:tc:opendocument:xmlns:container",
                "pkg": "http://www.idpf.org/2007/opf",
                "dc": "http://purl.org/dc/elements/1.1/",
            },
        )[0]

    # prepare to read from the .epub file
    try:
        zip_content = zipfile.ZipFile(fname)

        # find the contents metafile
        cfname = xpath(
            etree.fromstring(zip_content.read("META-INF/container.xml")),
            "n:rootfiles/n:rootfile/@full-path",
        )
        
        # grab the metadata block from the contents metafile
        metadata = xpath(
            etree.fromstring(zip_content.read(cfname)), "/pkg:package/pkg:metadata"
        )
        
        # repackage the data
        return {
            s: xpath(metadata, f"dc:{s}/text()")
            for s in ("title", "language", "creator", "date", "identifier")
        }
    except zipfile.BadZipFile:
        return {}
    except IndexError:
        return {}

def parse_filename(filename):
    # Remove file extension
    filename = os.path.splitext(filename)[0]
    
    # Extract title and author
    stripped_filename = filename.replace(" (Z-Library)", "").replace("...", "")
    match = re.match(r'(.*?)\s*\((.*?)\)', stripped_filename)
    if match:
        title = match.group(1).strip()
        author = match.group(2).strip()
    else:
        # If the pattern doesn't match, use the whole filename as title
        title = stripped_filename
        author = "Unknown"
    
    return title, author

def run_calibre_command(command):
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(command)}")
        print(f"Error output: {e.stderr}")
        return False, e.stderr

def process_file(file_path):
    print(f"Processing file: {file_path}")
    
    filename = os.path.basename(file_path)
    title, author = parse_filename(filename)
    
    # Check if the book already exists
    success, output = run_calibre_command([
        CALIBREDB, "list",
        "--with-library", LIBRARY_DIR,
        "--fields", "title,authors",
        "--search", f"title:\"={title}\" authors:\"={author}\""
    ])
    
    if not success:
        print(f"Failed to check for existing book, moving book to failed directory: {filename}")
        output_path = os.path.join(f"{OUTPUT_DIR}/failed", filename)
        shutil.move(file_path, output_path)
        return
    
    if output.replace("id title authors", "").strip():
        print(f"Book already exists in the library, moving book to skipped directory: {filename}")
        output_path = os.path.join(f"{OUTPUT_DIR}/skipped", filename)
        shutil.move(file_path, output_path)
        return
    # Import book with title and author
    success, output = run_calibre_command([
        CALIBREDB, "add",
        "--with-library", LIBRARY_DIR,
        "--title", title,
        "--authors", author,
        file_path
    ])
    
    # get imported book id from output
    match = re.search(r"Added book ids: (\d+)", output)
    if not success or not match:
        print(f"Failed to add book, moving book to failed directory: {filename}")
        print(f"Calibre output: \n{output}")  # Log the output if import failed
        output_path = os.path.join(f"{OUTPUT_DIR}/failed", filename)
        shutil.move(file_path, output_path)
        return
    
    book_id = match.group(1).strip()
    meta = epub_info(file_path)
    title = meta.get("title", title)
    author = meta.get("creator", author)
    
    # Fetch book metadata
    print(f"Fetching metadata for: {filename}")
    success, output = run_calibre_command([
        FETCH_BOOK_METADATA,
        "--title", title,
        "--authors", author,
        "--opf"
    ])

    if not success:
        print(f"Failed to fetch metadata for, moving book to failed directory: {filename}")
        output_path = os.path.join(f"{OUTPUT_DIR}/failed", filename)
        shutil.move(file_path, output_path)
        return
    
    # Write metadata to /tmp file
    with open(f"/tmp/metadata.opf", "w") as f:
        f.write(output)

    # Set OPF metadata for the book
    print(f"Setting metadata for: {filename}")
    success, _ = run_calibre_command([
        CALIBREDB, "set_metadata",
        "--with-library", LIBRARY_DIR,
        book_id, f"/tmp/metadata.opf",
    ])

    if not success:
        print(f"Failed to set metadata for, moving book to failed directory: {filename}")
        output_path = os.path.join(f"{OUTPUT_DIR}/failed", filename)
        shutil.move(file_path, output_path)
        return
    
    # Remove the original file
    # Move the original file to the output directory
    print(f"Moving book to imported directory: {filename}")
    output_path = os.path.join(f"{OUTPUT_DIR}/imported", filename)
    shutil.move(file_path, output_path)
    print(f"Processed and moved: {file_path}")

def main():
    ensure_directories_exist()
    processed_files = set()
    
    while True:
        for filename in os.listdir(INPUT_DIR):
            print(f"Checking file: {filename}")
            file_path = os.path.join(INPUT_DIR, filename)
            if os.path.isfile(file_path) and file_path not in processed_files:
                # print(f"Processing file: {file_path}")
                process_file(file_path)
                processed_files.add(file_path)
        
        # Remove processed files that no longer exist from the set
        processed_files = {f for f in processed_files if os.path.exists(f)}
        
        time.sleep(5)  # Wait for 5 seconds before checking again

if __name__ == "__main__":
    print("Starting ebook importer...")
    main()
