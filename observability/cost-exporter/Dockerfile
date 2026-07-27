FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir prometheus-client==0.21.1
COPY observability/cost-exporter/exporter.py /app/exporter.py
ENV PORT=9100
EXPOSE 9100
CMD ["python", "/app/exporter.py"]
