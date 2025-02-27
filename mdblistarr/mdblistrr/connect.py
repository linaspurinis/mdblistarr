import logging, time, json, re, requests
from urllib.parse import urlparse
from retrying import retry
from requests.exceptions import RequestException, JSONDecodeError, ConnectionError
from lxml import html

logging.basicConfig(format='%(asctime)s severity=%(levelname)s filename=%(filename)s line=%(lineno)s message="%(message)s"', level=logging.INFO)

headers = { 
    'accept':'*/*',
    'accept-encoding':'gzip, deflate, br',
    'accept-language':'en-GB,en;q=0.9,en-US;q=0.8,hi;q=0.7,la;q=0.6',
    'cache-control':'no-cache',
    'dnt':'1',
    'pragma':'no-cache',
    'referer':'https',
    'sec-fetch-mode':'no-cors',
    'sec-fetch-site':'cross-site',
    'user-agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36',
}

class Connect:
    def __init__(self):
        self.session = requests.Session()
        self.trace_mode = False

    def get_html(self, url, headers=headers, params=None, cookies=None):
        return html.fromstring(self.get(url, headers=headers, params=params, cookies=cookies).content)

    def get_json(self, url, json=None, headers=None, params=None, cookies=None):
        return self.get(url, json=json, headers=headers, params=params, cookies=cookies).json()

    @retry(stop_max_attempt_number=6, wait_fixed=10000)
    def get(self, url, json=None, headers=None, params=None, cookies=None):
        return self.session.get(url, json=json, headers=headers, params=params, cookies=cookies)

    def get_image_encoded(self, url):
        return base64.b64encode(self.get(url).content).decode('utf-8')

    def post_html(self, url, data=None, json=None, headers=None, cookies=None):
        return html.fromstring(self.post(url, data=data, json=json, headers=headers, cookies=cookies).content)

    def post_json(self, url, data=None, json=None, headers=None, params=None, cookies=None):
        try:
            response = self.post(url, data=data, json=json, headers=headers, params=params, cookies=cookies)
            if not response.text.strip():
                return {"error": "Empty response from server", "status_code": response.status_code}
            try:
                return response.json()
            except JSONDecodeError:
                return {
                    "error": "Invalid POST response",
                    "status_code": response.status_code,
                    "raw_response": response.text[:500]  # Limit output for debugging
                }
        except ConnectionError as e:
            return {"error": "Connection failed", "exception": str(e)}
        except RequestException as e:
            return {"error": "Request failed", "exception": str(e)}

    @retry(stop_max_attempt_number=6, wait_fixed=10000)
    def post(self, url, data=None, json=None, headers=None, params=None, cookies=None):
        return self.session.post(url, data=data, json=json, params=params, headers=headers, cookies=cookies)
