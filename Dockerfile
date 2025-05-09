FROM python:3.10

# Avoid interactive timezone config
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Taipei

# Install OS dependencies
RUN apt-get update && apt-get install -y \
    git wget curl ffmpeg tzdata \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install \
    torch torchvision torchaudio \
    beautifulsoup4 tqdm tiktoken\
    requests \
    apscheduler \
    pytz
RUN pip install git+https://github.com/openai/whisper.git
RUN pip install yt-dlp

# Copy your script files into the container
COPY . /app
WORKDIR /app

# Run fetch script by default
CMD ["python", "fetch_url.py"]

