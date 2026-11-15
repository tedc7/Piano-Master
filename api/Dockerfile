# Piano App API (arch §4, §5). Built and started on the piano server by piano-api-redeploy;
# the compose file runs it as uid 10001 with the database under /data (PIANO_DB).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# the songs a release brings to a server without song tools (tools/deploy.sh, v0.51): their own
# layer, kept from build to build while they don't change
ENV PIANO_APP_SONGS=/srv/available
COPY available /srv/available
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
