FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY subtitula ./subtitula
# yt-dlp habilita fuentes de YouTube; faster-whisper queda fuera para que la imagen pese poco.
RUN pip install --no-cache-dir . yt-dlp

COPY config ./config
COPY samples ./samples

ENV PYTHONUNBUFFERED=1 SUBTITULA_DATA=/data
VOLUME /data
EXPOSE 8000
CMD ["subtitula", "serve", "--port", "8000"]
