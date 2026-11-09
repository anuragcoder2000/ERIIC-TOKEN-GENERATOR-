FROM python:3.11-slim-bookworm

# Dependencies install karein
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
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Chrome for Testing v156 download aur install karein
RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/156.0.7778.97/linux64/chrome-linux64.zip -O /tmp/chrome.zip && \
    unzip /tmp/chrome.zip -d /opt/ && \
    ln -s /opt/chrome-linux64/chrome /usr/bin/google-chrome && \
    rm /tmp/chrome.zip

WORKDIR /app

# Python packages install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baaki code copy karein
COPY . .

# Env variables set karein
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/google-chrome

# Run Xvfb and App
CMD Xvfb :99 -screen 0 1024x768x24 -ac +extension GLX +render -noreset & \
    gunicorn --timeout 300 --workers 1 app:app