import os, requests, re
from typing import List, Dict

def brave_search(query: str, api_key: str, count: int = 10, offset: int = 0) -> List[Dict]:
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"X-Subscription-Token": api_key}
    params = {"q": query, "count": count, "offset": offset}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    out = []
    for item in (data.get("web") or {}).get("results") or []:
        out.append({
            "title": item.get("title",""),
            "link": item.get("url",""),
            "snippet": item.get("description","")
        })
    return out

def serpapi_search(query: str, api_key: str, num: int = 10, start: int = 0) -> List[Dict]:
    url = "https://serpapi.com/search.json"
    params = {"engine":"google", "q": query, "num": num, "start": start, "api_key": api_key}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    out = []
    for item in (data.get("organic_results") or []):
        out.append({
            "title": item.get("title",""),
            "link": item.get("link",""),
            "snippet": item.get("snippet","")
        })
    return out

def search_generic(query: str, max_results: int = 10, page: int = 1) -> List[Dict]:
    brave_key = os.environ.get("BRAVE_KEY")
    serp_key = os.environ.get("SERPAPI_KEY")
    offset = max(0, (page - 1) * max_results)
    if brave_key:
        try:
            return brave_search(query, brave_key, count=max_results, offset=offset)
        except Exception:
            pass
    if serp_key:
        try:
            return serpapi_search(query, serp_key, num=max_results, start=offset)
        except Exception:
            pass
    raise RuntimeError("No search API key available. Set BRAVE_KEY or SERPAPI_KEY.")

def build_people_query(role_terms: str, geo_terms: str, industry_terms: str) -> str:
    parts = ["site:linkedin.com/in"]
    if role_terms: parts.append(f"({role_terms})")
    if geo_terms: parts.append(f"({geo_terms})")
    if industry_terms: parts.append(f"({industry_terms})")
    parts.append("-jobs -hiring")
    return " ".join(parts)

def build_company_query(geo_terms: str, industry_terms: str) -> str:
    parts = ["site:linkedin.com/company"]
    if geo_terms: parts.append(f"({geo_terms})")
    if industry_terms: parts.append(f"({industry_terms})")
    return " ".join(parts)

def build_general_query(role_terms: str, geo_terms: str, industry_terms: str, target: str) -> str:
    aug = []
    if target.startswith("People"): aug.append("(team OR leadership OR about us OR staff OR directory)")
    if role_terms and target.startswith("People"): aug.append(f"({role_terms})")
    if geo_terms: aug.append(f"({geo_terms})")
    if industry_terms: aug.append(f"({industry_terms})")
    return " ".join(aug) if aug else "site:*.com"

def parse_title_for_person(title: str):
    t = title.replace("| LinkedIn","").strip()
    m = re.match(r"^(?P<name>[^–\-|]+)[–\-]\s*(?P<title>.+?)\s+at\s+(?P<company>.+)$", t, re.I)
    if m:
        return m.group("name").strip(), m.group("title").strip(), m.group("company").strip()
    parts = re.split(r"[–\-|]", t)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 3:
        name, job, company = parts[0], parts[1], parts[2]
        return name, job, company
    return t, "", ""
