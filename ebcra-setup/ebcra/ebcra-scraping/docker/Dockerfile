FROM python:3.13-slim

WORKDIR /ebcra-scraping

#Install bash
RUN apt-get update && apt-get install -y bash

#Upgrade PIP
RUN /usr/local/bin/python -m pip install --upgrade pip

#Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

#Install Playwright and Chromium with all system dependencies
RUN playwright install chromium --with-deps

#Fill in the font set --with-deps misses (seen as WOFF2 decompression
#warnings + rendering-fidelity gaps in production; a stripped-down font
#stack is a detectable tell as well as a cosmetic issue). fonts-noto-core
#(not the full fonts-noto meta-package, which pulls in every script and
#is 1GB+) covers Latin-script rendering, which is all the current targets need.
RUN apt-get install -y fonts-liberation fonts-noto-core

COPY / .

CMD tail -f /dev/null
