FROM python:3.11-slim

RUN groupadd -r agent && useradd -r -g agent -d /app -s /sbin/nologin agent

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcpworks_agent/ mcpworks_agent/
COPY entrypoint.py .

RUN chown -R agent:agent /app

USER agent

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()"

ENTRYPOINT ["python", "entrypoint.py"]
