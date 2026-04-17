FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy and install dependencies first (better caching)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Run the bot
CMD ["python", "bot.py"]