FROM python:3.7-alpine

ADD requirements.txt /app/
ADD *.py /app/

RUN python -m pip install -U -r /app/requirements.txt

WORKDIR /app
ENTRYPOINT ["/usr/local/bin/kopf", "run", "--standalone", "iam_mapping.py"]
