FROM python:3.9

# Install system dependencies for Manim
RUN apt-get update && apt-get install -y \
    ffmpeg \
    texlive \
    texlive-latex-extra \
    texlive-fonts-extra \
    texlive-science \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    python3-dev \
    build-essential \
    libgirepository1.0-dev \
    gir1.2-pango-1.0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the service file
COPY main.py .

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]