FROM ubuntu:22.04

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

ENV TZ=Europe/Berlin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && \
    apt-get install -y libcurl4-openssl-dev cmake libssl-dev build-essential automake pkg-config libtool libffi-dev libgmp-dev libyaml-cpp-dev && \
    apt-get install -y git && \
    apt-get install -y wget && apt-get install -y curl && \
    apt-get install -y software-properties-common

RUN apt-get install -y python3-distutils && \ 
    apt-get install -y python3-apt
    
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.8 libpython3.8-dev
    

RUN apt-get install -y python3-pip

RUN git clone https://github.com/ethereum/pyethereum && \
    cd ./pyethereum && \
    git checkout develop && \
    git checkout 3d5ec14032cc471f4dcfc7cc5c947294daf85fe0 && \
    pip3 install --default-timeout=100 . && \
    cd ../

WORKDIR /usr/src/core

ADD ./requirements.txt .

RUN pip3 install --default-timeout=100 -r ./requirements.txt

ADD . .

ENTRYPOINT ["python3", "./extractor.py"]
