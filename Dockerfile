# Specific version to maintain stability
FROM python:3.12.8-slim

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

# Widen the Websocket bridge to prevent it from crashing with heavy maps
ENV STREAMLIT_SERVER_MAX_MESSAGE_SIZE=500

# Blind Streamlit to temporary files, killing the loop
ENV STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

# Disable sending of metrics for speed boost
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false

# Expose Streamlit default port
EXPOSE 8501

# Command to run the Streamlit application
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501",  "--server.fileWatcherType=none", "--server.maxMessageSize=1000"]