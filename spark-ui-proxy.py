#!/usr/bin/env python
# MIT License
# 
# Copyright (c) 2016 Alexis Seigneurin
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import socketserver
import logging
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from html.parser import HTMLParser
import re

BIND_ADDR = os.environ.get("BIND_ADDR", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "80"))
URL_PREFIX = os.environ.get("URL_PREFIX", "").rstrip('/') + '/'
SPARK_MASTER_HOST = ""
SPARK_TITLE_PATTERN = r"Spark (?P<spark_type>\w+) at (?P<spark_url>\S+)"
URL_PATTERN = r"(?P<protocol>\w+://)?(?P<host>[-\w.]+):(?P<port>\d+)"
WORKER_HREF_PATTERN = r'(href="/proxy:)(spark-[-\w]+-worker-[-\w]+)(:)'


class SparkHTMLParser(HTMLParser):
    def __init__(self):
        self.title = False
        self.spark_title = None
        self.spark_type = None
        self.spark_url = None
        HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.title = False

    def handle_data(self, data):
        if self.title:
            if self.spark_type is not None or self.spark_url is not None:
                raise Exception(
                    "Spark data is already filled (orig title: {0}, current title: {1})".format(self.spark_title, data))
            self.spark_title = data
            try:
                spark_dict = re.search(SPARK_TITLE_PATTERN, data).groupdict()
                self.spark_type = spark_dict["spark_type"].lower()
                self.spark_url = spark_dict["spark_url"]
            except:
                pass


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Add an health checking endpoint.
        if self.path in ["/healthz"]:
            self.send_response(code=200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        # redirect if we are hitting the home page
        if self.path in ["", URL_PREFIX]:
            self.send_response(302)
            self.send_header("Location", URL_PREFIX + "proxy:" + SPARK_MASTER_HOST)
            self.end_headers()
            return
        self.proxyRequest(None)

    def do_POST(self):
        length = int(self.headers.get('content-length'))
        postData = self.rfile.read(length)
        self.proxyRequest(postData)

    def proxyRequest(self, data):
        targetHost, path = self.extractUrlDetails(self.path)
        targetUrl = "http://" + targetHost + path

        print("get: %s  host: %s  path: %s  target: %s" % (self.path, targetHost, path, targetUrl))

        try:
            proxiedRequest = urllib.request.urlopen(targetUrl, data)
        except Exception as ue:
            logging.error("Caught an exception trying to reach [ {0} ]".format(targetUrl))
            raise ue

        resCode = proxiedRequest.getcode()

        if resCode == 200:
            page = proxiedRequest.read()
            if not path.endswith(".png"):
                page = self.rewriteLinks(page, targetHost)
                page = self.rewriteWorkerLinks(page)
                page = self.removeDeadLinks(page)
            resContentType = proxiedRequest.info()["Content-Type"]
            self.send_response(200)
            self.send_header("Content-Type", resContentType)
            self.end_headers()
            self.wfile.write(page)
        elif resCode == 302:
            self.send_response(302)
            self.send_header("Location", URL_PREFIX + "proxy:" + SPARK_MASTER_HOST)
            self.end_headers()
        else:
            raise Exception(f"Unsupported response: {resCode}")

    def extractUrlDetails(self, path):
        if path.startswith(URL_PREFIX + "proxy:"):
            start_idx = len(URL_PREFIX) + 6  # len('proxy:') == 6
            idx = path.find("/", start_idx)
            targetHost = path[start_idx:] if idx == -1 else path[start_idx:idx]
            path = "" if idx == -1 else path[idx:]
        else:
            targetHost = SPARK_MASTER_HOST
            path = path
        return targetHost, path

    def rewriteLinks(self, page, targetHost):
        # Convert bytes to string for processing
        if isinstance(page, bytes):
            page = page.decode('utf-8')

        target = "{0}proxy:{1}/".format(URL_PREFIX, targetHost)
        page = page.replace('href="/', 'href="' + target)
        page = page.replace("'<div><a href=' + logUrl + '>'",
                            "'<div><a href=' + location.origin + logUrl.replace('http://', '/proxy:') + '>'")
        page = page.replace('href="log', 'href="' + target + 'log')
        page = page.replace('href="http://', 'href="' + URL_PREFIX + 'proxy:')
        page = page.replace('src="/', 'src="' + target)
        page = page.replace('action="', 'action="' + target)
        page = page.replace('"/api/v1/', '"' + target + 'api/v1/')
        page = page.replace('{{uiroot}}/history', '{{uiroot}}' + target + 'history')

        # Convert back to bytes for writing
        return page.encode('utf-8')

    def rewriteWorkerLinks(self, page):
        # Convert bytes to string for processing
        if isinstance(page, bytes):
            page = page.decode('utf-8')

        parser = SparkHTMLParser()
        parser.feed(page)
        if parser.spark_type == 'worker':
            worker_dict = re.search(URL_PATTERN, parser.spark_url).groupdict()
            page = re.sub(WORKER_HREF_PATTERN, r"\g<1>" + worker_dict['host'] + r"\g<3>", page)

        # Convert back to bytes if it was originally bytes
        return page.encode('utf-8') if isinstance(page, str) else page

    def removeDeadLinks(self, page):
        # Convert bytes to string for processing
        if isinstance(page, bytes):
            page = page.decode('utf-8')

        page = re.sub(r'<p><a href="/proxy:[-\w]+:\d+">Back to Master</a></p>', '', page)

        # Convert back to bytes
        return page.encode('utf-8')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: <proxied host:port> [<proxy port>]")
        sys.exit(1)

    SPARK_MASTER_HOST = sys.argv[1]

    if len(sys.argv) >= 3:
        SERVER_PORT = int(sys.argv[2])

    print("Starting server on http://{0}:{1}".format(BIND_ADDR, SERVER_PORT))


    class ForkingHTTPServer(socketserver.ForkingMixIn, HTTPServer):
        def finish_request(self, request, client_address):
            request.settimeout(30)
            HTTPServer.finish_request(self, request, client_address)


    server_address = (BIND_ADDR, SERVER_PORT)
    httpd = ForkingHTTPServer(server_address, ProxyHandler)
    httpd.serve_forever()
