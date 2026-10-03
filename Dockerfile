FROM python:3.10-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# git is needed if requirements.txt installs packages from GitHub;
# gcc/build-essential are needed to build tgcrypto and similar packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends git gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so Docker can cache this layer
COPY requirements.txt .
RUN pip install -U pip && pip install -r requirements.txt

# Copy the rest of the bot code
COPY . .

# Render sets PORT itself; this is only documentation
EXPOSE 8080

# Change bot.py if your repo starts differently (e.g. "python3 -m bot")
CMD ["python3", "bot.py"]
