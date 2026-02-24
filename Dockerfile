FROM python:3.11-slim

# Install system dependencies as root
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI v2
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws \
    && aws --version

# Create non-root user with home directory for AWS credentials
RUN groupadd -r lifecycle && useradd -r -g lifecycle -d /home/lifecycle -m -s /sbin/nologin lifecycle

# Set working directory
WORKDIR /work

# Copy requirements and install Python dependencies as root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.yaml .
COPY src/ ./src/
COPY entrypoint.sh .

# Make entrypoint executable and set ownership
RUN chmod +x entrypoint.sh \
    && chown -R lifecycle:lifecycle /work

# Switch to non-root user
USER lifecycle

# Default entrypoint
ENTRYPOINT ["./entrypoint.sh"]
