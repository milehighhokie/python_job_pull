import requests
import feedparser         # For parsing RSS feeds (Indeed)
from bs4 import BeautifulSoup  # For parsing HTML (Dice)
import csv
from datetime import datetime
from dotenv import load_dotenv
import os

# Define search keywords and locations
KEYWORDS = ["COBOL", "Python"]
LOCATION_LOCAL = "Denver"
LOCATION_REMOTE = "Remote"
load_dotenv()  # Loads variables from .env into environment

# API credentials
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

# zip_key = os.getenv("ZIPRECRUITER_API_KEY")

# Prepare a list to collect all job records
jobs = []

### 1. Fetch from Indeed (RSS feeds) ###
for keyword in KEYWORDS:
    for loc in [LOCATION_LOCAL, LOCATION_REMOTE]:
        query = f"q={requests.utils.requote_uri(keyword)}&l={requests.utils.requote_uri(loc)}"
        rss_url = f"https://www.indeed.com/rss?{query}"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            # e.g. "COBOL Developer – ABC Corp – Denver, CO"
            title = entry.get("title", "")
            # direct link to the job posting
            link = entry.get("link", "")
            # Indeed RSS typically includes the company and location in the title text.
            # We might attempt to split them out. For example, the title may be "JobTitle - Company (Location)".
            company = ""
            location = loc if loc != "Remote" else "Remote"
            if " – " in title:  # some feeds use dash or en dash as separator
                parts = title.split(" – ")
                title = parts[0].strip()
                if len(parts) > 1:
                    company = parts[1].strip()
            # Indeed's RSS 'summary' often contains a snippet of the job description.
            snippet = entry.get("summary", "") or entry.get("description", "")
            # e.g. "Tue, 29 Apr 2025 10:00:00 GMT"
            date_posted = entry.get("published", "")
            jobs.append({
                "Title": title,
                "Company": company,
                "Location": location,
                "Date": date_posted,
                "Snippet": snippet,
                "URL": link
            })

### 2. Fetch from Adzuna API ###
for keyword in KEYWORDS:
    # Search Denver area
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": 20,
        "what": "Python",
        "where": LOCATION_LOCAL,       # filter by Denver, CO
        "content-type": "application/json"
    }
    resp = requests.get(
        "https://api.adzuna.com/v1/api/jobs/us/search/1", params=params)
    if resp.status_code == 200:
        data = resp.json()
       # print(data)
        for result in data.get("results", []):
            title = result.get("title", "")
            company = result.get("company", {}).get("display_name", "")
            location = result.get("location", {}).get("display_name", "")
            # this is a snippet provided by Adzuna
            snippet = result.get("description", "")
            # ISO date string, e.g. "2025-04-28T12:34:56Z"
            date_posted = result.get("created", "")
            url = result.get("redirect_url", "")      # direct link to job
            jobs.append({
                "Title": title,
                "Company": company,
                "Location": location,
                "Date": date_posted,
                "Snippet": snippet,
                "URL": url
            })
    else:
        print(f"Adzuna API error: {resp.status_code} - {resp.text}")
    # (Optional) To include remote jobs via Adzuna, we could do a nationwide search and filter.
    # For example, remove the 'where' param or use a broad location, then check if the location or title contains "Remote".
    # Due to overlap with other sources, and since Adzuna doesn't have a specific remote filter, we mainly use it for location-specific results.

### 3. Fetch from ZipRecruiter API ###
for keyword in KEYWORDS:
    location = "Denver, CO"
    headers = {'User-Agent': 'Mozilla/5.0'}
    query = keyword.replace(" ", "+")
    loc = location.replace(" ", "+").replace(",", "%2C")
    url = f"https://www.ziprecruiter.com/candidate/search?search={query}&location={loc}"

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

#    jobs = []
    for card in soup.select("article.job_result"):
        title_tag = card.select_one("a.job_title")
        company_tag = card.select_one("a.t_org_link")
        location_tag = card.select_one("li.location")
        snippet_tag = card.select_one("div.job_snippet")
        date_tag = card.select_one("time")

        job = {
            "Title": title_tag.get_text(strip=True) if title_tag else "",
            "Company": company_tag.get_text(strip=True) if company_tag else "",
            "Location": location_tag.get_text(strip=True) if location_tag else location,
            "Date": date_tag.get("datetime") if date_tag else "",
            "Snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
            "URL": f"https://www.ziprecruiter.com{title_tag['href']}" if title_tag and title_tag.has_attr("href") else ""
        }
        jobs.append(job)


# Save to CSV
with open("ziprecruiter_jobs.csv", "w", newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(
        f, fieldnames=["Title", "Company", "Location", "Date", "Snippet", "URL"])
    writer.writeheader()
    for job in jobs:
        writer.writerow(job)

# print(f"Saved {len(jobs)} jobs to ziprecruiter_jobs.csv")

### 4. Fetch from Dice (scraping HTML) ###
for keyword in KEYWORDS:
    # We use location=Denver, CO to find local jobs (Dice will also list some remote jobs in results).
    search_url = f"https://www.dice.com/jobs?q={keyword}&location=Denver%2C%20CO"
    headers = {"User-Agent": "Mozilla/5.0"}  # impersonate a browser
    resp = requests.get(search_url, headers=headers)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        # Each job listing on Dice is typically contained in a card or list element.
        # (Note: The actual HTML structure might differ; adjust the selectors accordingly.)
        # placeholder class name; use real one from Dice HTML
        job_cards = soup.find_all('div', class_='card')
        for card in job_cards:
            # Extract title
            title_tag = card.find(
                ['h2', 'h3'], string=lambda text: text and keyword in text)
            title = title_tag.get_text().strip() if title_tag else ""
            # Extract company - often within an <h3> or <span> with company name
            company_tag = card.find('h3') or card.find(
                'span', attrs={"data-cy": "company-name"})
            company = company_tag.get_text().strip() if company_tag else ""
            # Extract location - maybe in a <span> with class for location or after a bullet
            location_tag = card.find('span', class_='job-location') or card.find(
                string=lambda text: "USA" in text or "Remote" in text)
            location = location_tag.strip() if location_tag else ""
            # Extract posted date or age (e.g., "Posted X days ago")
            date_tag = card.find(
                'span', string=lambda s: "Posted" in s or "hour" in s or "day" in s)
            date_posted = date_tag.get_text().strip() if date_tag else ""
            # Extract snippet of description - maybe a short summary paragraph
            snippet_tag = card.find(
                'div', class_='card-description') or card.find('p', class_='description')
            snippet = snippet_tag.get_text().strip() if snippet_tag else ""
            # Extract job URL from the title link
            link_tag = card.find('a', href=True)
            url = link_tag['href'] if link_tag else ""
            # If the link is relative (e.g., starts with "/jobs/"), prepend the domain
            if url and url.startswith("/"):
                url = "https://www.dice.com" + url
            # Only add if we found a title and link
            if title and url:
                jobs.append({
                    "Title": title,
                    "Company": company,
                    "Location": location,
                    "Date": date_posted,
                    "Snippet": snippet,
                    "URL": url
                })

### 5. Fetch from RemoteOK (remote jobs API) ###
resp = requests.get("https://remoteok.io/api",
                    headers={"User-Agent": "Mozilla/5.0"})
if resp.status_code == 200:
    try:
        data = resp.json()
    except ValueError:
        data = []
    for job in data:
        # The API may include a metadata object at the start; ensure we're looking at job entries
        if not isinstance(job, dict) or "position" not in job:
            continue
        title = job.get("position", "")
        company = job.get("company", "")
        location = job.get("location", "") or "Remote"
        date_str = job.get("date")  # e.g. "2025-04-29"
        # Or use epoch timestamp if provided:
        if not date_str and job.get("epoch"):
            try:
                date_obj = datetime.fromtimestamp(int(job["epoch"]))
                date_str = date_obj.strftime("%Y-%m-%d")
            except:
                date_str = ""
        # plain text description if available
        snippet = job.get("description_text", "") or ""
        url = job.get("url", "")  # link to the job on RemoteOK
        # Filter to include only jobs that mention COBOL or Python in title or tags
        tags = job.get("tags", [])
        # Check keyword presence (case-insensitive)
        if (any(k.lower() in title.lower() for k in KEYWORDS) or
                any(k.lower() in (",".join(tags)).lower() for k in KEYWORDS)):
            jobs.append({
                "Title": title,
                "Company": company,
                "Location": location,
                "Date": date_str,
                "Snippet": snippet[:200],  # take first 200 chars as snippet
                "URL": url
            })

# **Post-processing:** Remove duplicate entries (if any) based on URL or Title+Company
seen_urls = set()
unique_jobs = []
for job in jobs:
    if job["URL"] in seen_urls:
        continue
    seen_urls.add(job["URL"])
    unique_jobs.append(job)

# Write results to CSV
output_file = "daily_job_posts.csv"
with open(output_file, mode='w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(
        f, fieldnames=["Title", "Company", "Location", "Date", "Snippet", "URL"])
    writer.writeheader()
    for job in unique_jobs:
        writer.writerow(job)

print(f"Saved {len(unique_jobs)} job postings to {output_file}")
