FROM ubuntu:focal

WORKDIR /app

RUN apt update && apt install -y software-properties-common
RUN add-apt-repository -y ppa:deadsnakes/ppa && apt update
RUN apt install -y \
    net-tools \
    iputils-ping \
    iproute2 \
    python3.10

CMD ["/bin/bash"]