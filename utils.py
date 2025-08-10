import re, requests, tldextract, dns.resolver, time, json
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

COMMON_PATTERNS = [
    "first.last","f.last","first.l","first","last","firstlast","flast",
    "first_last","first-last","last.first","l.first","firstinitial.lastname"
]

HEADCOUNT_PATTERNS = [
    re.compile(r"(\d{1,4})\s*\+\s*employees", re.I),
    re.compile(r"(\d{1,4})\s*-\s*(\d{1,4})\s*employees", re.I),
    re.compile(r"(\d{1,4})\s*employees", re.I),
    re.compile(r"team\s+of\s+(\d{1,4})\b", re.I),
]

def normalize_domain(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if "://" in s:
        host = s.split("://",1)[1].split("/",1)[0]
    else:
        host = s.split("/",1)[0]
    ext = tldextract.extract(host)
    if not ext.suffix:
        return host.lower()
    return f"{ext.domain}.{ext.suffix}".lower()

def guess_domain_brave(company: str, brave_key: str) -> Optional[str]:
    url = "https://api.search.brave.com/res/v1/web/search"
    q = f'"{company}" (homepage OR website)'
    headers = {"X-Subscription-Token": brave_key}
    params = {"q": q, "count": 10}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for item in (data.get("web") or {}).get("results") or []:
            link = item.get("url","")
            dom = normalize_domain(link)
            if dom and dom not in {"linkedin.com","facebook.com","twitter.com","youtube.com","instagram.com"}:
                return dom
    except Exception:
        return None
    return None

def generate_candidates(first: str, last: str, domain: str) -> List[str]:
    f = (first or "").strip().lower()
    l = (last or "").strip().lower()
    if not (f and l and domain): return []
    fi, li = f[0], l[0]
    mapping = {
        "first.last": f"{f}.{l}@{domain}",
        "f.last": f"{fi}.{l}@{domain}",
        "first.l": f"{f}.{li}@{domain}",
        "first": f"{f}@{domain}",
        "last": f"{l}@{domain}",
        "firstlast": f"{f}{l}@{domain}",
        "flast": f"{fi}{l}@{domain}",
        "first_last": f"{f}_{l}@{domain}",
        "first-last": f"{f}-{l}@{domain}",
        "last.first": f"{l}.{f}@{domain}",
        "l.first": f"{li}.{f}@{domain}",
        "firstinitial.lastname": f"{fi}{l}@{domain}",
    }
    seen = set()
    out = []
    for pat in ["first.last","f.last","first.l","firstlast","flast","first","last","first_last","first-last","last.first","l.first","firstinitial.lastname"]:
        e = mapping.get(pat)
        if e and EMAIL_RE.match(e) and e not in seen:
            seen.add(e); out.append(e)
    return out

def has_mx(domain: str) -> List[str]:
    resolver = dns.resolver.Resolver()
    resolver.timeout = 4.0
    resolver.lifetime = 4.0
    try:
        answers = resolver.resolve(domain, 'MX', lifetime=4.0)
        hosts = [str(r.exchange).rstrip(".") for r in sorted(answers, key=lambda r: r.preference)]
        if hosts:
            return hosts
    except Exception:
        pass
    for rr in ("A","AAAA"):
        try:
            resolver.resolve(domain, rr, lifetime=4.0)
            return [domain]
        except Exception:
            continue
    return []

def validate_email_no_smtp(email: str) -> Dict[str, str]:
    out = {"email": email, "status": "", "reason": "", "mx_hosts": ""}
    if not EMAIL_RE.match(email):
        out.update(status="invalid", reason="bad_syntax"); return out
    domain = email.rsplit("@",1)[1]
    mx = has_mx(domain)
    out["mx_hosts"] = ",".join(mx)
    if not mx:
        out.update(status="invalid", reason="no_mx_or_dns")
    else:
        out.update(status="valid", reason="mx_present")
    return out

def fetch_html(url: str, timeout: int = 12) -> Optional[str]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent":"Eval/0.1 (+info)"})
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type",""):
            return r.text
    except requests.RequestException:
        return None
    return None

def estimate_headcount_from_html(html: str) -> Optional[int]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = script.string
            if not data:
                continue
            obj = json.loads(data)
            objs = obj if isinstance(obj, list) else [obj]
            for o in objs:
                for k in ["numberOfEmployees","employees","employee","staff"]:
                    val = o.get(k)
                    if isinstance(val, dict) and "value" in val and isinstance(val["value"], int):
                        return val["value"]
                    if isinstance(val, int):
                        return val
        except Exception:
            continue
    for pat in HEADCOUNT_PATTERNS:
        m = pat.search(text)
        if m:
            if len(m.groups()) == 2 and m.group(2):
                try:
                    lo = int(m.group(1)); hi = int(m.group(2))
                    return int((lo + hi)//2)
                except Exception:
                    continue
            else:
                try:
                    return int(m.group(1))
                except Exception:
                    continue
    return None

def estimate_headcount(domain: str) -> Optional[int]:
    if not domain: return None
    urls = [f"https://{domain}/", f"https://{domain}/about"]
    for url in urls:
        html = fetch_html(url)
        if not html: continue
        v = estimate_headcount_from_html(html)
        if isinstance(v, int) and v > 0: return v
        time.sleep(0.8)
    return None
