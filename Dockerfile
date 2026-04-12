FROM python:3
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /usr/src/app
COPY ./requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN apt-get update
COPY ./mdblistarr /usr/src/app/
RUN mkdir -p /usr/src/db/
ENV PORT=5353
EXPOSE 5353
COPY ./django-entrypoint.sh /
RUN chmod +x /django-entrypoint.sh
CMD ["/django-entrypoint.sh"]
