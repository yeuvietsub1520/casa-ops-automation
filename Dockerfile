FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 1000 app && mkdir /data && chown app /data
COPY app ./app
ENV PYTHONUNBUFFERED=1 PORT=8080 BOOKINGS_CSV=/data/bookings.csv TZ=Asia/Ho_Chi_Minh
USER app
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/health')"
CMD ["python", "-m", "app.server"]
