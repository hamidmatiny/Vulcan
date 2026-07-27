FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir prometheus-client==0.21.1
COPY observability/gpu-metrics/synthetic-dcgm/exporter.py /app/exporter.py
ENV PORT=9400
EXPOSE 9400
CMD ["python", "/app/exporter.py"]
