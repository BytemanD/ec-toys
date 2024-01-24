FROM ubuntu

RUN apt-get install python

ARG DATE

RUN echo $DATE
RUN cd /root/ec-toys \
    && python --version \
    && python -m pip wheel --prefer-binary --wheel-dir=dist --no-deps ./
