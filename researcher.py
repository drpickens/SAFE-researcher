#!/usr/bin/env python3
"""SAFE Researcher Agent

Runs twice weekly (Tuesday & Friday) to surface new articles relevant to the
SAFE framework and AI use in medical education. Searches PubMed, arXiv,
Semantic Scholar, and the Arise Network.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# How far back to search (slightly more than 3.5 days to avoid gaps at edges)
DAYS_BACK = 8

PUBMED_QUERIES = [
    # Bedside learner population: residents, interns, fellows, clinical-year students
    "artificial intelligence residents interns clinical training",
    "AI deskilling residents physicians clinical skills",
    "large language model clinical reasoning residency training",
    "ChatGPT AI use residents interns bedside",
    "AI clinical decision support residents postgraduate training",
    "AI adoption residents interns fellows postgraduate",
    "automation bias clinical decision support residents trainees",
    # Clerkship / MS3-MS4 (at the bedside, not pre-clinical)
    "AI clerkship clinical year medical student bedside",
    # Faculty teaching with residents at bedside
    "AI teaching framework attending resident bedside supervision",
    "LLM AI clinical tool safety residents HIPAA hallucination",
]

ARXIV_QUERIES = [
    "AI deskilling residents interns clinical reasoning bedside",
    "LLM clinical reasoning expert prompt resident trainee",
    "NOHARM clinical safety large language model benchmark",
    "automation bias AI clinical decision resident physician",
]

SEMANTIC_SCHOLAR_QUERIES = [
    "AI deskilling never-skilling residents interns fellows clinical training",
    "expert clinical prompting AI diagnostic reasoning resident trainee bedside",
    "structured AI use bedside teaching attending resident supervision",
]

ARISE_QUERIES = [
    "NOHARM clinical safety benchmark LLM",
    "arise network clinical AI evaluation",
    "MAST medical AI safety test",
]

# --- Relevance scoring keywords ---

# High value: bedside learner population and SAFE-specific themes
SAFE_HIGH_VALUE = [
    # Target learner population — residents, interns, fellows, clinical-year students
    "resident", "residents", "intern", "interns",
    "fellow", "fellows", "fellowship",
    "postgraduate", "post-graduate", "PGY",
    "clerkship", "clinical year", "MS3", "MS4",
    "junior doctor", "house officer", "trainee", "trainees",
    # Faculty/attending context (SAFE is faculty-facing)
    "attending", "faculty", "supervisor", "supervision",
    "bedside teaching", "clinical supervision", "ward rounds",
    # Core SAFE themes
    "clinical reasoning", "diagnostic reasoning",
    "knowledge retention", "learning outcomes",
    "never-skilling", "mis-skilling", "deskilling",
    "cognitive crutch", "automation bias",
    "clinical problem representation", "expert prompt",
    "AI teaching framework", "structured ai use",
]

AI_KEYWORDS = [
    "artificial intelligence", "large language model", "llm", "chatgpt", "gpt",
    "machine learning", "generative ai", "claude", "gemini", "foundation model",
    "openevidence", "uptodate", "doximity",
]

FRAMEWORK_KEYWORDS = [
    "framework", "curriculum", "structured", "pedagogical",
    "skill acquisition", "cognitive load",
    "diagnostic", "clinical decision", "benchmark",
    "deskilling", "critical appraisal", "red-team",
]

# Extra boost: topics directly cited or presented in both workshops
SAFE_SPECIFIC = [
    "deskilling", "never-skilling", "mis-skilling", "cognitive crutch",
    "knowledge retention", "DEFT-AI", "thinking habits model",
    "arise network", "NOHARM", "MAST", "healthbench",
    "clinical safety", "AI adoption", "unstructured ai",
    "automation bias", "alert fatigue", "AI hallucination",
    "clinical problem representation", "semantic qualifier",
    "expert context", "pre-test probability", "bayesian",
    "HIPAA AI", "de-identification", "sanctioned tool",
    "QI quality improvement AI", "bedside AI",
    "penda health", "AI error medical",
    "resident AI", "intern AI", "trainee AI use",
]

# Terms that lower priority — pre-clinical population, not the SAFE target
DEPRIORITIZE = [
    "undergraduate", "preclinical", "pre-clinical",
    "first year medical student", "second year medical student",
    "ms1", "ms2", "year 1", "year 2",
    "nursing student", "pharmacy student",
]


# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------

def pubmed_search(query: str, days_back: int = DAYS_BACK) -> list[dict]:
    """Search PubMed via NCBI E-utilities. Returns list of article dicts."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    min_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")

    search_params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": query,
        "retmax": 8,
        "sort": "pub_date",
        "retmode": "json",
        "datetype": "edat",
        "mindate": min_date,
        "maxdate": "3000/01/01",
        "tool": "SAFE-researcher",
        "email": "safe-researcher@drpickens.com",
    })

    try:
        with urllib.request.urlopen(f"{base}esearch.fcgi?{search_params}", timeout=15) as r:
            data = json.loads(r.read())
        ids = data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"  [PubMed search error] {query}: {e}", file=sys.stderr)
        return []

    if not ids:
        return []

    time.sleep(0.4)

    fetch_params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
        "tool": "SAFE-researcher",
        "email": "safe-researcher@drpickens.com",
    })

    try:
        with urllib.request.urlopen(f"{base}efetch.fcgi?{fetch_params}", timeout=20) as r:
            xml_data = r.read()
    except Exception as e:
        print(f"  [PubMed fetch error] {query}: {e}", file=sys.stderr)
        return []

    articles = []
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []

    for article in root.findall(".//PubmedArticle"):
        try:
            pmid = article.findtext(".//PMID", "")
            title = article.findtext(".//ArticleTitle", "").strip()
            abstract = article.findtext(".//AbstractText", "").strip()
            journal = article.findtext(".//Journal/Title", "")

            authors = []
            for author in article.findall(".//Author")[:3]:
                last = author.findtext("LastName", "")
                first = author.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {first[0]}." if first else last)

            year = (
                article.findtext(".//PubDate/Year")
                or article.findtext(".//PubDate/MedlineDate", "")[:4]
            )

            if not title:
                continue

            articles.append({
                "source": "PubMed",
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "abstract": (abstract[:350] + "…") if len(abstract) > 350 else abstract,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "_id": f"pmid:{pmid}",
            })
        except Exception:
            continue

    return articles


def arxiv_search(query: str, days_back: int = DAYS_BACK) -> list[dict]:
    """Search arXiv for recent preprints."""
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": 6,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })

    try:
        with urllib.request.urlopen(
            f"http://export.arxiv.org/api/query?{params}", timeout=20
        ) as r:
            xml_data = r.read()
    except Exception as e:
        print(f"  [arXiv error] {query}: {e}", file=sys.stderr)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []

    cutoff = datetime.now() - timedelta(days=days_back)
    articles = []

    for entry in root.findall("atom:entry", ns):
        try:
            published_str = entry.findtext("atom:published", "", ns)
            if not published_str:
                continue
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00")).replace(tzinfo=None)
            if published < cutoff:
                continue

            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
            arxiv_id = (entry.findtext("atom:id", "", ns) or "").strip()

            link = arxiv_id
            for link_el in entry.findall("atom:link", ns):
                if link_el.get("type") == "text/html":
                    link = link_el.get("href", arxiv_id)
                    break

            authors = [
                (a.findtext("atom:name", "", ns) or "").strip()
                for a in entry.findall("atom:author", ns)[:3]
            ]

            if not title:
                continue

            articles.append({
                "source": "arXiv",
                "title": title,
                "authors": authors,
                "journal": "arXiv preprint",
                "year": published.strftime("%Y"),
                "abstract": (abstract[:350] + "…") if len(abstract) > 350 else abstract,
                "url": link,
                "_id": f"arxiv:{arxiv_id}",
            })
        except Exception:
            continue

    return articles


def semantic_scholar_search(query: str, days_back: int = DAYS_BACK) -> list[dict]:
    """Search Semantic Scholar for recent papers."""
    cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    params = urllib.parse.urlencode({
        "query": query,
        "fields": "title,authors,year,abstract,externalIds,venue,publicationDate",
        "limit": 8,
        "publicationDateOrYear": f"{cutoff_date}:",
    })

    req = urllib.request.Request(
        f"https://api.semanticscholar.org/graph/v1/paper/search?{params}",
        headers={"User-Agent": "SAFE-researcher/1.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"  [Semantic Scholar error] {query}: {e}", file=sys.stderr)
        return []

    articles = []
    for paper in data.get("data", []):
        try:
            ext_ids = paper.get("externalIds") or {}
            pmid = ext_ids.get("PubMed", "")
            doi = ext_ids.get("DOI", "")
            arxiv_id = ext_ids.get("ArXiv", "")

            if pmid:
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                _id = f"pmid:{pmid}"
            elif doi:
                url = f"https://doi.org/{doi}"
                _id = f"doi:{doi}"
            elif arxiv_id:
                url = f"https://arxiv.org/abs/{arxiv_id}"
                _id = f"arxiv:{arxiv_id}"
            else:
                url = ""
                _id = f"s2:{paper.get('paperId', '')}"

            authors = [a.get("name", "") for a in (paper.get("authors") or [])[:3]]
            abstract = paper.get("abstract") or ""
            title = paper.get("title") or ""

            if not title:
                continue

            articles.append({
                "source": "Semantic Scholar",
                "title": title,
                "authors": authors,
                "journal": paper.get("venue") or "",
                "year": str(paper.get("year") or ""),
                "abstract": (abstract[:350] + "…") if len(abstract) > 350 else abstract,
                "url": url,
                "_id": _id,
            })
        except Exception:
            continue

    return articles


def arise_network_check() -> list[dict]:
    """Check the Arise Network for new content and search for NOHARM/MAST papers."""
    articles = []

    # Always include the live leaderboard as a standing check-in item
    articles.append({
        "source": "Arise Network",
        "title": "Arise Network — NOHARM MAST Live Leaderboard",
        "authors": ["Arise Network"],
        "journal": "bench.arise-ai.org",
        "year": str(datetime.now().year),
        "abstract": (
            "Check the live leaderboard for the latest NOHARM clinical safety scores "
            "across frontier AI models. Updated as new models are evaluated. "
            "Current leaders as of the slide deck: AMBOSS LiSA 1.0 (62.3%), Gemini 2.5 Pro (59.9%), "
            "GPT-5 (58.3%), Claude Sonnet 4.5 (58.2%) — all above human physicians (46.0%)."
        ),
        "url": "https://bench.arise-ai.org",
        "_id": "arise:leaderboard",
    })

    # Search Semantic Scholar for Arise / NOHARM / MAST papers
    for q in ARISE_QUERIES:
        try:
            params = urllib.parse.urlencode({
                "query": q,
                "fields": "title,authors,year,abstract,externalIds,venue",
                "limit": 5,
            })
            req = urllib.request.Request(
                f"https://api.semanticscholar.org/graph/v1/paper/search?{params}",
                headers={"User-Agent": "SAFE-researcher/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())

            for paper in data.get("data", [])[:3]:
                ext_ids = paper.get("externalIds") or {}
                pmid = ext_ids.get("PubMed", "")
                doi = ext_ids.get("DOI", "")
                arxiv_id = ext_ids.get("ArXiv", "")

                if pmid:
                    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                    _id = f"pmid:{pmid}"
                elif doi:
                    url = f"https://doi.org/{doi}"
                    _id = f"doi:{doi}"
                elif arxiv_id:
                    url = f"https://arxiv.org/abs/{arxiv_id}"
                    _id = f"arxiv:{arxiv_id}"
                else:
                    _id = f"s2:{paper.get('paperId', '')}"
                    url = ""

                abstract = paper.get("abstract") or ""
                title = paper.get("title") or ""
                if not title:
                    continue

                articles.append({
                    "source": "Arise Network",
                    "title": title,
                    "authors": [a.get("name", "") for a in (paper.get("authors") or [])[:3]],
                    "journal": paper.get("venue") or "",
                    "year": str(paper.get("year") or ""),
                    "abstract": (abstract[:350] + "…") if len(abstract) > 350 else abstract,
                    "url": url,
                    "_id": _id,
                })

            time.sleep(1.0)
        except Exception as e:
            print(f"  [Arise search error] {q}: {e}", file=sys.stderr)

    return articles


# ---------------------------------------------------------------------------
# Deduplication & scoring
# ---------------------------------------------------------------------------

def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicates by canonical ID, then by normalized title."""
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    unique = []

    for a in articles:
        _id = a.get("_id", "")
        title_key = "".join(c for c in a["title"].lower() if c.isalnum())[:80]

        if _id and _id != "arise:leaderboard" and _id in seen_ids:
            continue
        if title_key and title_key in seen_titles:
            continue

        if _id:
            seen_ids.add(_id)
        if title_key:
            seen_titles.add(title_key)
        unique.append(a)

    return unique


def score_relevance(article: dict) -> int:
    """
    Score 0–10 for relevance to the SAFE framework.
    Target population: residents, interns, fellows, and MS3/MS4 on clerkship.
    Faculty using SAFE with bedside learners.
    """
    text = (article["title"] + " " + article.get("abstract", "")).lower()
    score = 0

    # Bedside learner population and SAFE themes (high weight)
    for kw in SAFE_HIGH_VALUE:
        if kw in text:
            score += 3

    # AI presence (required but only counted once)
    for kw in AI_KEYWORDS:
        if kw in text:
            score += 2
            break

    # Framework/educational method terms
    for kw in FRAMEWORK_KEYWORDS:
        if kw in text:
            score += 1

    # SAFE-specific topics (extra boost)
    for kw in SAFE_SPECIFIC:
        if kw in text:
            score += 2

    # Penalize pre-clinical / non-bedside populations
    for kw in DEPRIORITIZE:
        if kw in text:
            score -= 3

    # Boost Arise Network items
    if article["source"] == "Arise Network":
        score += 3

    # Boost high-impact journals
    journal = article.get("journal", "").lower()
    for j in ["nejm", "lancet", "jama", "bmj", "nature", "science", "npj", "jmir"]:
        if j in journal:
            score += 2
            break

    return max(0, min(score, 10))


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def stars(score: int) -> str:
    filled = min(score, 5)
    return "★" * filled + "☆" * (5 - filled)


def format_article(a: dict) -> str:
    """Format a single article as a markdown block."""
    url = a.get("url", "")
    title = a.get("title") or "Untitled"
    link = f"[{title}]({url})" if url else title

    authors = ", ".join(a.get("authors") or []) or "Authors unknown"
    journal = a.get("journal") or ""
    year = a.get("year") or ""
    abstract = a.get("abstract") or ""
    relevance = a.get("relevance")

    meta_parts = [p for p in [journal, year, authors] if p]
    meta = " · ".join(meta_parts)

    block = f"### {link}\n"
    block += f"*{meta}*"
    if relevance is not None:
        block += f" &nbsp;·&nbsp; {stars(relevance)} ({relevance}/10)"
    block += "\n\n"
    if abstract:
        block += f"> {abstract}\n\n"
    return block


def next_run_date() -> str:
    today = datetime.now()
    for i in range(1, 8):
        nxt = today + timedelta(days=i)
        if nxt.weekday() in (1, 4):  # 1=Tuesday, 4=Friday
            return nxt.strftime("%A, %B %-d")
    return "Next Tuesday or Friday"


def build_digest(all_articles: list[dict], run_date: str) -> str:
    for a in all_articles:
        a["relevance"] = score_relevance(a)

    arise = [a for a in all_articles if a["source"] == "Arise Network"]

    others = [a for a in all_articles if a["source"] != "Arise Network"]

    # Preprints: arXiv source or no venue/journal (not yet peer-reviewed)
    preprints = sorted(
        [a for a in others if a["source"] == "arXiv" or "arxiv" in a.get("journal", "").lower()],
        key=lambda x: x["relevance"],
        reverse=True,
    )[:5]

    # Peer-reviewed: PubMed or Semantic Scholar with a journal/venue
    peer_reviewed = sorted(
        [a for a in others if a["source"] != "arXiv" and "arxiv" not in a.get("journal", "").lower()],
        key=lambda x: x["relevance"],
        reverse=True,
    )[:5]

    lines = [
        f"# SAFE Researcher Digest — {run_date}",
        "",
        "> Tailored for two workshops: **Faculty Workshop** (AI & the Learner — ED Retreat) and "
        "**Learner Workshop** (AI at the Bedside — Legacy RCH).",
        f"> **Sources:** PubMed · arXiv · Semantic Scholar · Arise Network &nbsp;|&nbsp; "
        f"**Period:** last {DAYS_BACK} days &nbsp;|&nbsp; **Next run:** {next_run_date()}",
        "",
        "---",
        "",
        "## Arise Network",
        "_Check for new NOHARM/MAST benchmark updates and Arise-affiliated publications._",
        "",
    ]

    if arise:
        for a in arise[:6]:
            lines.append(format_article(a))
    else:
        lines.append("_No new Arise Network content detected this period._\n")

    lines += [
        "---",
        "",
        "## Top 5 Peer-Reviewed Articles",
        "",
        "_Prioritizing studies of **residents, interns, fellows, and MS3/MS4 on clerkship** — "
        "the bedside learner population SAFE is designed for. Topics: deskilling · never-skilling · "
        "mis-skilling · automation bias · expert prompting · AI teaching frameworks · "
        "faculty supervision at the bedside._",
        "",
    ]

    if peer_reviewed:
        for i, a in enumerate(peer_reviewed, 1):
            lines.append(f"**{i}.**\n\n" + format_article(a))
    else:
        lines.append("_No peer-reviewed articles found this period._\n")

    lines += [
        "---",
        "",
        "## Top 5 Preprints",
        "",
        "_Fast-moving arXiv preprints — where NOHARM, Shen & Tamkin, and Lopez et al. "
        "appeared before peer review. Same population priority: residents, interns, fellows, clerkship._",
        "",
    ]

    if preprints:
        for i, a in enumerate(preprints, 1):
            lines.append(f"**{i}.**\n\n" + format_article(a))
    else:
        lines.append("_No preprints found this period._\n")

    lines += [
        "---",
        "",
        "## Search Coverage",
        "",
        "| Source | Queries |",
        "|--------|---------|",
        "| **PubMed** | AI deskilling physicians · AI medical education framework faculty · "
        "LLM clinical reasoning teaching · structured AI curriculum · AI adoption trainees · "
        "ChatGPT knowledge retention · AI diagnostic accuracy students · automation bias · "
        "clinical problem representation · AI tool safety HIPAA |",
        "| **arXiv** | AI deskilling never-skilling clinical · LLM expert prompt medical student · "
        "NOHARM clinical safety benchmark · automation bias AI clinical |",
        "| **Semantic Scholar** | AI medical education deskilling never-skilling framework · "
        "expert clinical prompting AI diagnostic · structured AI bedside teaching |",
        "| **Arise Network** | bench.arise-ai.org leaderboard · NOHARM MAST papers · Arise AI evaluation |",
        "",
        "## Workshop Topics Tracked",
        "**Faculty Workshop (AI & the Learner — ED Retreat)**",
        "- Deskilling evidence (colonoscopy RCT, radiology, pathology, surgery)",
        "- Never-skilling: cognitive friction removed → foundational skills not built",
        "- AI frameworks for teaching: DEFT-AI · THM · SAFE",
        "- AI adoption rates among trainees and attendings",
        "- Faculty development and structured AI supervision",
        "- Arrive Network / NOHARM / MAST / HealthBench benchmarks",
        "",
        "**Learner Workshop (AI at the Bedside — Legacy RCH)**",
        "- Never-skilling and mis-skilling: RCT evidence",
        "- Automation bias and uncritical AI acceptance",
        "- Expert vs. learner clinical problem representation and prompting",
        "- Clinical AI tool safety: HIPAA, hallucination, sanctioned tools",
        "- AI clinical performance benchmarks vs. published tools (UpToDate, OpenEvidence)",
        "- How SAFE builds reasoning skills case-by-case",
        "",
        "_Generated by [SAFE Researcher Agent](../../blob/main/researcher.py) · "
        "[View all digests](../../issues?label=digest)_",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    run_date = datetime.now().strftime("%Y-%m-%d")
    print(f"SAFE Researcher starting — {run_date}", flush=True)

    all_articles: list[dict] = []

    print("Searching PubMed…", flush=True)
    for q in PUBMED_QUERIES:
        results = pubmed_search(q)
        print(f"  '{q[:50]}' → {len(results)} results", flush=True)
        all_articles.extend(results)
        time.sleep(0.4)

    print("Searching arXiv…", flush=True)
    for q in ARXIV_QUERIES:
        results = arxiv_search(q)
        print(f"  '{q[:50]}' → {len(results)} results", flush=True)
        all_articles.extend(results)
        time.sleep(0.5)

    print("Searching Semantic Scholar…", flush=True)
    for q in SEMANTIC_SCHOLAR_QUERIES:
        results = semantic_scholar_search(q)
        print(f"  '{q[:50]}' → {len(results)} results", flush=True)
        all_articles.extend(results)
        time.sleep(1.2)

    print("Checking Arise Network…", flush=True)
    arise_results = arise_network_check()
    print(f"  → {len(arise_results)} items", flush=True)
    all_articles.extend(arise_results)

    before = len(all_articles)
    all_articles = deduplicate(all_articles)
    print(f"Deduplication: {before} → {len(all_articles)} unique articles", flush=True)

    digest = build_digest(all_articles, run_date)

    output_path = f"digest-{run_date}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(digest)

    print(f"Digest written to {output_path} ({len(all_articles)} articles)", flush=True)


if __name__ == "__main__":
    main()
