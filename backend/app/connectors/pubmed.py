from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

import httpx

from ..config import get_settings
from .base import BaseConnector, FetchedDoc

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedConnector(BaseConnector):
    name = "pubmed"

    def fetch(self, scope: dict[str, Any]) -> list[FetchedDoc]:
        settings = get_settings()
        pubmed = (scope.get("connectors") or {}).get("pubmed") or {}
        query = (pubmed.get("query") or scope.get("topic") or "").strip()
        if not query:
            return []
        max_results = int(pubmed.get("max_results") or 20)
        sort = (pubmed.get("sort") or "").strip() or None

        ids = self._esearch(query, max_results, settings, sort=sort)
        if not ids:
            return []
        # NCBI asks for pacing without API key (~3 rps); be conservative
        time.sleep(0.4)
        articles = self._efetch(ids, settings)
        docs: list[FetchedDoc] = []
        for art in articles:
            doc = FetchedDoc(
                connector=self.name,
                title=art["title"],
                raw_text=art["text"],
                url=art.get("url"),
                authors=art.get("authors"),
                published_at=art.get("published_at"),
                metadata={
                    "pmid": art.get("pmid"),
                    "journal": art.get("journal"),
                },
            )
            if self.passes_filters(doc, scope):
                docs.append(doc)
        return docs

    def _request(self, url: str, settings, retries: int = 3) -> httpx.Response:
        headers = {"User-Agent": f"ResearchBriefStudio/0.1 ({settings.ncbi_email})"}
        last_exc: Exception | None = None
        with httpx.Client(timeout=60.0, headers=headers) as client:
            for attempt in range(retries):
                try:
                    resp = client.get(url)
                    if resp.status_code in {429, 500, 502, 503}:
                        time.sleep(0.8 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    return resp
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    time.sleep(0.8 * (attempt + 1))
        if last_exc:
            raise last_exc
        raise RuntimeError("PubMed request failed")

    def _esearch(
        self, query: str, max_results: int, settings, *, sort: str | None = None
    ) -> list[str]:
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "email": settings.ncbi_email,
            "tool": "research_brief_studio",
        }
        if sort:
            params["sort"] = sort
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
        url = f"{EUTILS}/esearch.fcgi?{urlencode(params)}"
        resp = self._request(url, settings)
        data = resp.json()
        return data.get("esearchresult", {}).get("idlist", [])

    def _efetch(self, ids: list[str], settings) -> list[dict[str, Any]]:
        params = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml",
            "email": settings.ncbi_email,
            "tool": "research_brief_studio",
        }
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
        url = f"{EUTILS}/efetch.fcgi?{urlencode(params)}"
        resp = self._request(url, settings)
        xml_text = resp.text

        root = ET.fromstring(xml_text)
        articles: list[dict[str, Any]] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = _text(article.find(".//PMID")) or ""
            title = _text(article.find(".//ArticleTitle")) or f"PMID {pmid}"
            abstract_parts = [
                _text(n) for n in article.findall(".//Abstract/AbstractText") if _text(n)
            ]
            abstract = "\n".join(abstract_parts) or "(No abstract available)"
            authors = []
            for author in article.findall(".//AuthorList/Author"):
                last = _text(author.find("LastName")) or ""
                fore = _text(author.find("ForeName")) or ""
                name = f"{fore} {last}".strip()
                if name:
                    authors.append(name)
            journal = _text(article.find(".//Journal/Title"))
            year = _text(article.find(".//PubDate/Year"))
            month = _text(article.find(".//PubDate/Month"))
            day = _text(article.find(".//PubDate/Day")) or "01"
            published = None
            if year:
                published = f"{year}-{_month_to_num(month)}-{day.zfill(2)}"
            text = f"{title}\n\n{abstract}"
            if journal:
                text = f"{title}\nJournal: {journal}\n\n{abstract}"
            articles.append(
                {
                    "pmid": pmid,
                    "title": title,
                    "text": text,
                    "authors": ", ".join(authors[:12]) if authors else None,
                    "published_at": published,
                    "journal": journal,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                }
            )
        return articles


def _text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    return "".join(node.itertext()).strip() or None


def _month_to_num(month: str | None) -> str:
    if not month:
        return "01"
    mapping = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    key = month.strip().lower()[:3]
    if key in mapping:
        return mapping[key]
    if month.isdigit():
        return month.zfill(2)
    return "01"
