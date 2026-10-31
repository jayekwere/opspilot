FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS web
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY tsconfig.json index.html ./
COPY web ./web
RUN npm run build

FROM python:3.14-slim@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPSPILOT_CONTAINER=1 OPSPILOT_STATE=/state
WORKDIR /app
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.2 && python -m pip install --no-cache-dir --require-hashes -r requirements.lock && groupadd -g 10001 opspilot && useradd -u 10001 -g 10001 -M opspilot && mkdir /state && chown 10001:10001 /state
COPY opspilot ./opspilot
COPY --from=web /build/dist ./dist
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=2)"]
CMD ["python", "-m", "opspilot.cli", "serve"]

FROM python:3.14-slim@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8 AS test
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-dev.lock ./
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.2 && python -m pip install --no-cache-dir --require-hashes -r requirements-dev.lock && groupadd -g 10001 opspilot && useradd -u 10001 -g 10001 -M opspilot && mkdir /reports && chown 10001:10001 /reports
COPY opspilot ./opspilot
COPY tests ./tests
COPY scripts ./scripts
COPY pyproject.toml ./
USER 10001:10001
CMD ["python", "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider"]
