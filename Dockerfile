FROM python:3.12-slim
WORKDIR /app
COPY app ./app
ENV PYTHONUNBUFFERED=1 PORT=8080 BOOKINGS_CSV=/data/bookings.csv
VOLUME /data
EXPOSE 8080
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/health')"
CMD ["python", "-m", "app.server"]
