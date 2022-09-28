# Build ubuntu:20.04 for VNC environment

FROM ubuntu:20.04
MAINTAINER taichi.iki@gmail.com

# Install

## Set DEBIAN_FRONTEND=noninteractive to skip the time-zone selection
ENV DEBIAN_FRONTEND noninteractive

## Utilities
RUN apt update \
    && apt install -y curl wget zip supervisor git
RUN mkdir -p /var/log/supervisor

## Python
RUN apt update \
    && apt install -y python3.9 python3-pip

## Virtual display and VNC server
RUN apt update \
    && apt install -y xvfb x11vnc

## Browser (google-chrome)
RUN apt update \
    && apt install -y gpg-agent \
    && curl -LO https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && (dpkg -i ./google-chrome-stable_current_amd64.deb || apt-get install -fy) \
    && curl -sSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add \
    && rm google-chrome-stable_current_amd64.deb
RUN curl -OL https://chromedriver.storage.googleapis.com/104.0.5112.79/chromedriver_linux64.zip \
    && unzip chromedriver_linux64.zip \
    && rm chromedriver_linux64.zip 

## Fonts
# fonts-noto is required to render japanese characters.
# You can ommit the package if you do not use them.
RUN apt update \
    && apt install -y ttf-ubuntu-font-family fonts-noto \
    && fc-cache -fv

## MiniWoB
RUN cd /usr/local \
    && git clone https://github.com/stanfordnlp/miniwob-plusplus.git

## Replace jquery ui with the newer version
RUN rm -r /usr/local/miniwob-plusplus/html/core/jquery-ui
COPY jquery-ui-1.13.2 /usr/local/miniwob-plusplus/html/core/jquery-ui

## Patch for jscolor to use scaled document
RUN mv /usr/local/miniwob-plusplus/html/core/jscolor.min.js /usr/local/miniwob-plusplus/html/core/_jscolor.min.js
RUN cat /usr/local/miniwob-plusplus/html/core/_jscolor.min.js | sed \
    -e 's!\(s.x-e._pointerOrigin.x\)!(\1)/JSC_SCALE!' \
    -e 's!\(s.y-e._pointerOrigin.y\)!(\1)/JSC_SCALE!' \
    -e 's!\(i.y-e._pointerOrigin.y\)!(\1)/JSC_SCALE!' \
    -e 's!\(e.picker.wrap.style.left=n\)!\1/JSC_SCALE!' \
    -e 's!\(e.picker.wrap.style.top=r\)!\1/JSC_SCALE!' > /usr/local/miniwob-plusplus/html/core/jscolor.min.js
RUN echo 'var JSC_SCALE=1.0;' >> /usr/local/miniwob-plusplus/html/core/jscolor.min.js

## Python libraries
RUN python3.9 -m pip install -U pip
RUN python3.9 -m pip install selenium tornado Pillow requests numpy pyyaml

## vncdotool requirements
COPY src/vncdotool_mini/requirements.txt /tmp/requirements.txt
RUN python3.9 -m pip install -r /tmp/requirements.txt

## Copy source codes
RUN mkdir /src
COPY src /src

# Boot the system
# We depend on supervisor to manage multiple processes
# See supervisord.conf for the detail
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord"]
#CMD ["python3.9", "-u", "/src/controller.py"]
