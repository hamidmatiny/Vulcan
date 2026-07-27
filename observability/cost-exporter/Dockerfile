FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir prometheus-client==0.21.1
COPY observability/cost-exporter/exporter.py /app/exporter.py
COPY observability/cost-exporter/gpu-hour-assumptions.json /app/gpu-hour-assumptions.json
ENV PORT=9100
ENV VULCAN_GPU_HOUR_ASSUMPTIONS=/app/gpu-hour-assumptions.json
EXPOSE 9100
CMD ["python", "/app/exporter.py"]
