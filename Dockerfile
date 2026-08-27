# Use official Python slim image for smaller size
FROM python:3.11.9-slim

# Set environment variables to prevent Python from buffering output
# and to disable Python bytecode compilation
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory inside the container
WORKDIR /app

# Install system dependencies required for cryptography and other packages
# slim image doesn't include build tools by default
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first (for better layer caching)
# This way, if requirements don't change, Docker reuses cached layer
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application code
COPY . .

# Create a non-root user to run the bot (security best practice)
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Command to run the bot
CMD ["python", "bot.py"]
