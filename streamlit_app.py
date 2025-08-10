import os, streamlit as st, pandas as pd
from utils import normalize_domain, guess_domain_brave, generate_candidates, validate_email_no_smtp, estimate_headcount
from search import (
    search_generic,
    build_people_query, build_company_query, build_general_query, parse_title_for_person
)

st.set_page_config(page_title="Eval — Lead Finder", page_icon="✅", layout="wide")

# ---------- Styles ----------
st.markdown("""
<style>
:root { --accent:#22c55e; --card:#111318; --muted:#0d0f13; --txt:#e6e6e6; }
.block-container{padding-top:2rem;padding-bottom:2rem;}
h1, h2, h3 { color: var(--txt); }
.small-muted{color:#9aa0a6;font-size:0.85rem;}
.card{background:var(--card); border:1px solid #20242c; border-radius:1rem; padding:1rem; box-shadow:0 0 0 rgba(0,0,0,0);}
.row{display:flex; gap:1rem; align-items:flex-start;}
.col{flex:1;}
.btn-primary button{background:var(--accent)!important; border:none; color:#0b0f0c!important; font-weight:700;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1>Eval ✅ Lead Finder</h1>", unsafe_allow_html=True)
st.markdown('<div class="small-muted">Find HR/benefits decision-makers, infer company emails, and validate via DNS/MX — no SMTP needed.</div>', unsafe_allow_html=True)
st.write("")

# Presets
US_STATES = ["", "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA",
             "ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
             "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"]
COUNTRIES = ["", "United States", "Canada", "United Kingdom", "Australia"]
TOP25_INDUSTRIES = [
    "", "Health Care & Social Assistance","Retail Trade","Professional, Scientific & Technical Services",
    "Manufacturing","Accommodation & Food Services","Construction","Administrative & Support Services",
    "Transportation & Warehousing","Finance & Insurance","Real Estate & Rental & Leasing","Educational Services",
    "Wholesale Trade","Information","Arts, Entertainment & Recreation","Other Services (except Public Admin)",
    "Public Administration","Utilities","Agriculture, Forestry, Fishing & Hunting","Mining, Quarrying, Oil & Gas",
    "Management of Companies & Enterprises","Waste Management & Remediation Services","Postal & Courier",
    "Telecommunications","Computer Systems & Design"
]
ROLE_PRESETS = [
    "Head of HR","HR Director","VP HR","Benefits Manager","Benefits Specialist",
    "People Operations","Chief People Officer","HR Manager","HRBP",
    "CFO","Controller","Finance Director","Operations Director","Office Manager"
]

key_present = bool(os.environ.get("BRAVE_KEY") or st.secrets.get("BRAVE_KEY") or os.environ.get("SERPAPI_KEY") or st.secrets.get("SERPAPI_KEY"))
if not key_present:
    st.error("Missing search API key. Set BRAVE_KEY (recommended) or SERPAPI_KEY in env or Streamlit secrets.")
    st.stop()

# ---------- Controls in 3 columns ----------
st.markdown('<div class="row">', unsafe_allow_html=True)
st.markdown('<div class="col card">', unsafe_allow_html=True)
target = st.selectbox("Target", ["People (roles)", "Companies"], index=0)
source = st.selectbox("Search source", ["LinkedIn only", "General web", "Both"], index=0)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="col card">', unsafe_allow_html=True)
st.markdown("**Geo filters**")
country = st.selectbox("Country", COUNTRIES, index=COUNTRIES.index("United States"))
state = st.selectbox("US State (2-letter)", US_STATES, index=US_STATES.index("AZ"))
city = st.text_input("City (optional)", "")
zipcode = st.text_input("ZIP code (optional)", "")
area_code = st.text_input("Area code (optional)", "")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="col card">', unsafe_allow_html=True)
st.markdown("**Industry & Roles**")
industry = st.selectbox("Industry (Top 25)", TOP25_INDUSTRIES, index=TOP25_INDUSTRIES.index("Health Care & Social Assistance"))
roles = st.multiselect("Roles (People targeting)", ROLE_PRESETS, default=["Benefits Manager","Head of HR","HR Director","CFO"])
per_page = st.slider("Results per page", 10, 50, 20, step=5)
page = st.number_input("Page", min_value=1, value=1, step=1)
skip_seen = st.checkbox("Skip previously seen", value=True)
remember_seen = st.checkbox("Persist seen list", value=True)
st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

with st.container():
    st.write("")
    run = st.button("Search", type="primary", use_container_width=True)

# Seen utilities
def load_seen(path="seen_urls.csv"):
    try:
        df = pd.read_csv(path)
        return set(df["url"].dropna().tolist())
    except Exception:
        return set()

def save_seen(seen, path="seen_urls.csv"):
    try:
        pd.DataFrame({"url": sorted(seen)}).to_csv(path, index=False)
    except Exception:
        pass

seen = load_seen() if remember_seen else set()

def join_terms(terms):
    terms = [t for t in terms if t]
    return " OR ".join(sorted(set(terms))) if terms else ""

def geo_terms():
    parts = []
    if city: parts.append(city)
    if state: parts.append(state)
    if zipcode: parts.append(zipcode)
    if area_code: parts.append(area_code)
    if country: parts.append(country)
    return join_terms(parts)

def role_terms():
    return " OR ".join(roles) if (target.startswith("People") and roles) else ""

def industry_terms():
    return industry if industry else ""

def run_query(kind: str):
    g = geo_terms(); r = role_terms(); i = industry_terms()
    if kind == "LinkedIn":
        q = build_people_query(r, g, i) if target.startswith("People") else build_company_query(g, i)
    else:
        q = build_general_query(r if target.startswith("People") else "", g, i, target)
    results = search_generic(q, max_results=per_page, page=page)
    return q, results

if run:
    queries_results = []
    if source in ("LinkedIn only", "Both"):
        q, res = run_query("LinkedIn"); queries_results.append(("LinkedIn", q, res))
    if source in ("General web", "Both"):
        q, res = run_query("General"); queries_results.append(("General", q, res))

    all_rows = []
    for label, q, results in queries_results:
        st.markdown(f"### {label}")
        st.code(q, language="text")
        rows = [{"source": label, "title": r["title"], "url": r["link"], "snippet": r["snippet"]} for r in results]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
        all_rows.extend(results)

    unique = []
    urls_seen_this_run = set()
    for r in all_rows:
        u = r["link"]
        if u in urls_seen_this_run: continue
        if skip_seen and u in seen: continue
        urls_seen_this_run.add(u); unique.append(r)
    if remember_seen:
        seen |= urls_seen_this_run; save_seen(seen)
    st.success(f"{len(unique)} unique URLs after dedupe.")

    st.markdown("### Enrich & validate")
    enriched = []; brave_key = os.environ.get("BRAVE_KEY") or st.secrets.get("BRAVE_KEY")
    for r in unique:
        if target.startswith("People") and (("linkedin.com/in" in r["link"]) or "LinkedIn" in r["title"]):
            name, title, company_name = parse_title_for_person(r["title"])
        else:
            name, title, company_name = ("", "", r["title"].replace("| LinkedIn","").strip())

        domain=""; emails=[]
        if company_name and brave_key:
            domain = guess_domain_brave(company_name, brave_key) or ""
        domain = normalize_domain(domain) if domain else ""

        headcount=None
        if domain:
            try: headcount = estimate_headcount(domain)
            except Exception: headcount=None

        first,last="",""
        if name:
            parts = name.split()
            if len(parts) >= 2: first, last = parts[0], parts[-1]
        if first and last and domain:
            emails = generate_candidates(first, last, domain)

        vals = [validate_email_no_smtp(e) for e in emails]
        best = next((v for v in vals if v["status"]=="valid"), vals[0] if vals else None)

        enriched.append({
            "name": name, "title": title, "company": company_name, "domain": domain,
            "headcount": headcount if headcount is not None else "",
            "email": best["email"] if best else "", "status": best["status"] if best else "",
            "reason": best["reason"] if best else "", "mx_hosts": best["mx_hosts"] if best else "",
            "url": r["link"]
        })

    out = pd.DataFrame(enriched)
    st.dataframe(out, use_container_width=True)
    st.download_button("Download eval_leads.csv", out.to_csv(index=False).encode("utf-8"), file_name="eval_leads.csv", mime="text/csv")
else:
    st.markdown("<span class='small-muted'>Set filters then hit Search.</span>", unsafe_allow_html=True)
