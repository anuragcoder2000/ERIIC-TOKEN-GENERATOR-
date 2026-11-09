# 1. Bullseye ki jagah Bookworm (Debian 12) use karein
FROM python:3.11-slim-bookworm

# 2. System dependencies install karein (Chromium ke liye zaroori)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    libxi6 \
    libnss3 \
    libxss1 \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libu2f-udev \
    chromium \
    chromium-driver \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 3. Working directory set karein
WORKDIR /app

# 4. Python dependencies install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Baaki code copy karein
COPY . .

# 6. Chrome binary ka path set karein
ENV CHROME_BIN=/usr/bin/chromium

# 7. Xvfb display set karein (headless mode ke liye)
ENV DISPLAY=:99

# 8. Start command (Xvfb ke saath)
CMD Xvfb :99 -screen 0 1024x768x24 -ac +extension GLX +render -noreset & \
    gunicorn --timeout 300 --workers 1 app:app