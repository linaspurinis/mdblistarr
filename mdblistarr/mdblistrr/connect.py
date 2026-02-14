import logging, time, json as jsonlib, re, requests, gzip, zlib
from urllib.parse import urlparse
from tenacity import retry, stop_after_attempt, wait_fixed
from requests.exceptions import RequestException, JSONDecodeError, ConnectionError
from lxml import html

logging.basicConfig(format='%(asctime)s severity=%(levelname)s filename=%(filename)s line=%(lineno)s message="%(message)s"', level=logging.INFO)

DEFAULT_HEADERS = {
    'accept':'*/*',
    # Avoid advertising brotli unless we're sure the runtime can decode it.
    'accept-encoding':'gzip, deflate',
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

    def _redact_url(self, url: str) -> str:
        try:
            p = urlparse(url)
            return f"{p.scheme}://{p.netloc}{p.path}"
        except Exception:
            return "<unparseable_url>"

    def _decode_response_bytes(self, response):
        """
        Best-effort decode for cases where the server returns compressed bytes
        but headers are missing/incorrect, so requests doesn't auto-decompress.
        """
        raw = response.content or b""
        if not raw:
            return ""

        enc = (response.headers.get("content-encoding") or "").lower().strip()
        try_order = []
        if enc:
            try_order.append(enc)

        # gzip magic bytes: 1f 8b 08
        if len(raw) >= 3 and raw[0:3] == b"\x1f\x8b\x08":
            try_order.append("gzip")

        try_order.extend(["deflate", "br"])

        data = raw
        for e in try_order:
            try:
                if e == "gzip":
                    data = gzip.decompress(raw)
                    break
                if e == "deflate":
                    try:
                        data = zlib.decompress(raw)
                    except Exception:
                        data = zlib.decompress(raw, -zlib.MAX_WBITS)
                    break
                if e == "br":
                    try:
                        import brotli  # type: ignore
                    except Exception:
                        continue
                    data = brotli.decompress(raw)
                    break
            except Exception:
                continue

        try:
            return data.decode("utf-8")
        except Exception:
            return data.decode("utf-8", errors="replace")

    def get_html(self, url, headers=DEFAULT_HEADERS, params=None, cookies=None):
        return html.fromstring(self.get(url, headers=headers, params=params, cookies=cookies).content)

    def get_json(self, url, json=None, headers=None, params=None, cookies=None):
        try:
            response = self.get(url, json=json, headers=headers, params=params, cookies=cookies)
            text = response.text or ""
            if not text.strip():
                return {
                    "error": "empty_response",
                    "status_code": response.status_code,
                    "url": self._redact_url(url),
                }

            try:
                return response.json()
            except (JSONDecodeError, ValueError):
                return {
                    "error": "invalid_json_response",
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "url": self._redact_url(url),
                    "raw_response": text[:500],
                }
        except ConnectionError as e:
            return {"error": "connection_failed", "exception": str(e), "url": self._redact_url(url)}
        except RequestException as e:
            return {"error": "request_failed", "exception": str(e), "url": self._redact_url(url)}

    @retry(stop=stop_after_attempt(6), wait=wait_fixed(10))
    def get(self, url, json=None, headers=None, params=None, cookies=None):
        if headers is None:
            headers = DEFAULT_HEADERS
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
                decoded = self._decode_response_bytes(response)
                if decoded.strip():
                    try:
                        return jsonlib.loads(decoded)
                    except Exception:
                        pass
                return {
                    "error": "Invalid POST response",
                    "status_code": response.status_code,
                    "raw_response": (decoded or response.text)[:500]  # Limit output for debugging
                }
        except ConnectionError as e:
            return {"error": "Connection failed", "exception": str(e)}
        except RequestException as e:
            return {"error": "Request failed", "exception": str(e)}

    @retry(stop=stop_after_attempt(6), wait=wait_fixed(10))
    def post(self, url, data=None, json=None, headers=None, params=None, cookies=None):
        if headers is None:
            headers = DEFAULT_HEADERS
        return self.session.post(url, data=data, json=json, params=params, headers=headers, cookies=cookies)
