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

COPY / .

CMD tail -f /dev/null
