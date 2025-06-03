# -----------------------------------------------------------
# Unified Python + Node.js image for Semantic-Kernel agentic backend
# -----------------------------------------------------------
FROM nikolaik/python-nodejs:python3.12-nodejs20-slim

WORKDIR /usr/src/app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/usr/src/app/src \
    # Define where sentence-transformers should look for/store models.
    # This path will be within the image.
    SENTENCE_TRANSFORMERS_HOME=/usr/src/app/.cache/sentence_transformers

# Create the cache directory early.
RUN mkdir -p $SENTENCE_TRANSFORMERS_HOME

# Install Python dependencies
COPY src/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- Download and cache the sentence transformer model ---
# This layer will only be rebuilt if requirements.txt changes or this line changes.
# It runs BEFORE your application code is copied.
RUN python -c "from sentence_transformers import SentenceTransformer; print('Downloading/caching model all-MiniLM-L6-v2...'); SentenceTransformer('all-MiniLM-L6-v2'); print('Model all-MiniLM-L6-v2 cached.')"

# Install MCP server globally
# This layer will be cached if the above layers are cached.
RUN npm install -g @elastic/mcp-server-elasticsearch

# Copy source code
# Changes in ./src will only invalidate this layer and subsequent ones.
COPY src /usr/src/app/src
# COPY .env /usr/src/app/.env # .env should not be copied into the image. It is provided by docker-compose.

EXPOSE 8888

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8888"]
