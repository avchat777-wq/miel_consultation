FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0
COPY event_invite /app/event_invite
RUN mkdir -p /data && chown -R 10001:10001 /data /app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "event_invite.app:app", "--host", "0.0.0.0", "--port", "8000"]
