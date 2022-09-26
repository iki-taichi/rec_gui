FROM ubuntu:20.04
MAINTAINER taichi.iki@gmail.com

## Set DEBIAN_FRONTEND=noninteractive to skip the time-zone selection
ENV DEBIAN_FRONTEND noninteractive

RUN apt update \
    && apt install -y python3.9 python3-pip
    
RUN mkdir /app
WORKDIR /app

COPY requirements.txt ./
RUN python3.9 -m pip install -U pip wheel
RUN python3.9 -m pip install -r ./requirements.txt

COPY src/ ./src/
COPY templates/ ./templates/

RUN python3.9 src/dataset_utils.py

CMD ["python3.9", "-u", "src/server.py"]