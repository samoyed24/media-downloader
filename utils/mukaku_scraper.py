#!/usr/bin/env python3
"""
web5.mukaku.com 影视磁力链接爬虫
"""

import requests
import time


class MukakuScraper:
    BASE_URL = "https://web5.mukaku.com/prod/api/v1"
    APP_ID = "83768d9ad4"
    IDENTITY = "23734adac0301bccdcb107c4aa21f96c"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://web5.mukaku.com/",
        "Accept": "application/json, text/plain, */*",
    }

    def __init__(self, delay: float = 5.0, max_retries: int = 3):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.delay = delay
        self.max_retries = max_retries
        self._last_request_time = 0

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint: str, params: dict = None) -> dict:
        params = params or {}
        params["app_id"] = self.APP_ID
        params["identity"] = self.IDENTITY
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=5)
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if resp.status_code in (502, 503, 504) and attempt < self.max_retries - 1:
                    wait = self.delay * (attempt + 2)
                    time.sleep(wait)
                    continue
                raise
            data = resp.json()

            if data.get("success"):
                return data

            code = data.get("code")
            msg = data.get("message", "")
            if code in (10000, 10107) and attempt < self.max_retries - 1:
                wait = self.delay * (attempt + 2)
                time.sleep(wait)
                continue
            raise Exception(f"API Error [{code}]: {msg}")

    def search(self, keyword: str) -> list:
        """搜索影视，返回结果列表"""
        data = self._get("getVideoList", {"sb": keyword})
        return data.get("data", {}).get("data", [])

    def get_detail(self, doub_id: int) -> dict:
        """获取影视详情 (使用 doub_id，即豆瓣ID)"""
        data = self._get("getVideoDetail", {"id": doub_id})
        return data.get("data", {})

    def get_magnets(self, doub_id: int) -> dict:
        """获取磁力链接，按画质分组，包含影视详情"""
        detail = self.get_detail(doub_id)
        ecca = detail.get("ecca", {})
        return {
            "title": detail.get("title"),
            "year": detail.get("years"),
            "doub_id": doub_id,
            "image": detail.get("image"),
            "quality_groups": ecca,
            # 影视详情
            "doub_score": detail.get("doub_score"),
            "doub_score_peo_num": detail.get("doub_score_peo_num"),
            "IMDB_score": detail.get("IMDB_score"),
            "IMDB_score_peo_num": detail.get("IMDB_score_peo_num"),
            "abstract": detail.get("abstract"),
            "director": detail.get("director"),
            "performer": detail.get("performer"),
            "class": detail.get("class"),
            "production_area": detail.get("production_area"),
            "episodes": detail.get("episodes"),
            "language": detail.get("language"),
        }

