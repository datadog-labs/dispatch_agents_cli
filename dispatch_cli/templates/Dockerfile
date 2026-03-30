# syntax=docker/dockerfile:1.4
FROM $BASE_IMAGE

COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISPATCH_AGENT_NAME=$DISPATCH_AGENT_NAME

WORKDIR /app

$SYSTEM_PACKAGES_STEP

# Copy local dependencies BEFORE copying pyproject.toml so uv can resolve them
$LOCAL_DEPS_COPY

# Copy dependency files first for better caching
COPY pyproject.toml* uv.lock* requirements*.txt ./

$LOCAL_DEPS_PATH_FIX

$DEPENDENCY_INSTALL_STEP

# Copy the rest of the project
COPY . /app

# Fix paths again after copying the full project (in case pyproject.toml was overwritten)
$LOCAL_DEPS_PATH_FIX

# Copy schema extraction script
COPY .dispatch/extract_schemas.py /app/.dispatch/extract_schemas.py

# Extract handler schemas and generate compliance report
# Mount .env file as a secret if provided (extract_schemas.py will load it)
RUN --mount=type=secret,id=dotenv,target=/app/.env \
    uv run python /app/.dispatch/extract_schemas.py

EXPOSE 50051

# Run from /app so UV can find the project environment
CMD ["uv", "run", "python", ".dispatch/__dispatch_listener__.py"]
