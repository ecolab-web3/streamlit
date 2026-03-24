# Use python:3.12-slim as lightweight base with clear dependencies
FROM python:3.12-slim

# Prevent interactive prompts during apt-get
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# Set the working directory
WORKDIR /app

# Copy the system packages list to install GDAL and required binaries
COPY packages.txt .

# Install system dependencies defined in packages.txt
RUN apt-get update && \
    xargs -a packages.txt apt-get install -y --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy python requirements
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose Streamlit default port
EXPOSE 8501

# Command to run the Streamlit application
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
