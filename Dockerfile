FROM python:3-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /usr/src/app
COPY ./requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends libxml2-dev libxslt-dev gcc && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN mkdir -p /usr/src/db/
COPY ./mdblistarr /usr/src/app/
ENV PORT=5353
EXPOSE 5353
COPY ./django-entrypoint.sh /
RUN chmod +x /django-entrypoint.sh
CMD ["/django-entrypoint.sh"]
