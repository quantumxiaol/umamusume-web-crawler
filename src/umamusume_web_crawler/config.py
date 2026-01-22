from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parents[1]


@dataclass
class Config:
    user_agent: str = "UmamusumeWebCrawler/1.0"

    # Proxy settings
    http_proxy: str | None = None
    https_proxy: str | None = None

    # Google Search settings
    google_api_key: str = ""
    google_cse_id: str = ""

    crawler_pruned_threshold: float = 0.3
    crawler_pruned_min_words: int = 5
    crawler_timeout_s: float = 300.0

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Config":
        env = environ or os.environ
        threshold_raw = env.get("CRAWLER_PRUNED_THRESHOLD")
        min_words_raw = env.get("CRAWLER_PRUNED_MIN_WORDS")
        timeout_raw = env.get("CRAWLER_TIMEOUT_S")
        threshold = (
            cls.crawler_pruned_threshold
            if threshold_raw in (None, "")
            else float(threshold_raw)
        )
        min_words = (
            cls.crawler_pruned_min_words
            if min_words_raw in (None, "")
            else int(min_words_raw)
        )
        timeout = (
            cls.crawler_timeout_s
            if timeout_raw in (None, "")
            else float(timeout_raw)
        )
        return cls(
            user_agent=env.get("USER_AGENT", cls.user_agent),
            http_proxy=env.get("HTTP_PROXY"),
            https_proxy=env.get("HTTPS_PROXY"),
            google_api_key=env.get("GOOGLE_API_KEY", ""),
            google_cse_id=env.get("GOOGLE_CSE_ID", ""),
            crawler_pruned_threshold=threshold,
            crawler_pruned_min_words=min_words,
            crawler_timeout_s=timeout,
        )

    def update_from_env(self, environ: dict[str, str] | None = None) -> None:
        updated = self.from_env(environ=environ)
        for field in fields(self):
            setattr(self, field.name, getattr(updated, field.name))

    def apply_overrides(self, **overrides: object) -> None:
        for key, value in overrides.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def validate_web_tools(self) -> None:
        missing = []
        if not self.google_api_key:
            missing.append("GOOGLE_API_KEY")
        if not self.google_cse_id:
            missing.append("GOOGLE_CSE_ID")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

    def proxy_url(self) -> str | None:
        if self.http_proxy:
            return self.http_proxy
        if self.https_proxy:
            return self.https_proxy
        return None


config = Config.from_env()
