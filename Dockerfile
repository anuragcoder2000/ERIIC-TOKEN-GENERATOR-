# 1. Bullseye base image use karein (Trixie se avoid karne ke liye)
FROM python:3.10-slim-bullseye

# 2. System dependencies update karein
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

# 3. Google Chrome Stable install karein (official .deb se)
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb

# 4. Working directory set karein
WORKDIR /app

# 5. Python dependencies install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Baaki code copy karein
COPY . .

# 7. Chrome binary ka path set karein (undetected-chromedriver ke liye zaroori)
ENV CHROME_BIN=/usr/bin/google-chrome

# 8. Xvfb display set karein (headless mode ke liye)
ENV DISPLAY=:99

# 9. Start command (Xvfb ke saath)
CMD Xvfb :99 -screen 0 1024x768x24 -ac +extension GLX +render -noreset & \
    gunicorn --timeout 300 --workers 1 app:app