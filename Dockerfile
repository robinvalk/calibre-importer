FROM python:3.12-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    xz-utils \
    xdg-utils \
    libopengl0 \
    libxcb-cursor0 \
    libgl1-mesa-glx \
    libegl1 \
    libxkbcommon0 \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

# Install Calibre
RUN wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh | sh /dev/stdin

# Add Calibre to PATH
ENV PATH="/opt/calibre:${PATH}"

# Set up working directory
WORKDIR /app

# Set up input and output directories
RUN mkdir -p /mnt/input /mnt/output /mnt/library

# Verify Calibre installation
RUN calibre --version && calibredb --version && fetch-ebook-metadata --version

# Set the QT_QPA_PLATFORM environment variable
ENV QT_QPA_PLATFORM=offscreen

RUN pip install --no-cache-dir \
    lxml

# Copy the Python script
COPY ebook_import.py .

CMD ["python3", "-u", "ebook_import.py"]
