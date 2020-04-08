FROM python:3.8-alpine

RUN apk add build-base
ADD . /app/
RUN python -m pip install -U -r /app/requirements.txt

WORKDIR /app
ENTRYPOINT ["/usr/local/bin/kopf", "run", "--standalone", "iam_mapping.py"]
