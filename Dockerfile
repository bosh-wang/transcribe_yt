FROM python:3.10

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Taipei

# Install OS dependencies
RUN apt-get update && apt-get install -y \
    git wget curl ffmpeg tzdata \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy your script files into the container
COPY . /app

# Default command
CMD ["python", "fetch_url.py"]

