#!/usr/bin/env python3

import json
import time
import requests
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PORT = 8080
EXCLUDED_KEYWORDS = re.compile(r'\b(PSA|SGC|CGC|BGS|BVG|GAI|GRADED|GRADE|SLAB|SLABBED|LOT|PANEL|COLLECTION|SET)\b', re.IGNORECASE)

# Global session and token storage
session = requests.Session()
last_auth_time = 0
AUTH_LIFETIME = 3600  # Refresh tokens every hour

def refresh_tokens():
    """Spins up the browser to clear Cloudflare and harvest active session cookies."""
    global last_auth_time, session
    print("[*] Initializing browser handshake to refresh security tokens...")
    
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
    
    driver = uc.Chrome(options=options, version_main=148)
    try:
        driver.get("https://130point.com")
        wait = WebDriverWait(driver, 15)
        search = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="search"]')))
        
        # Quick dummy transaction to establish clearance telemetry footprint
        search.click()
        search.send_keys("ping")
        time.sleep(0.3)
        
        submit = driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Search"]')
        submit.click()
        
        for _ in range(12):
            if driver.execute_script("return document.readyState") == "complete":
                break
            time.sleep(0.5)
            
        selenium_cookies = driver.get_cookies()
        new_session = requests.Session()
        for cookie in selenium_cookies:
            new_session.cookies.set(cookie['name'], cookie['value'])
            
        session = new_session
        last_auth_time = time.time()
        print("[+] Security clearance tokens successfully updated.")
    except Exception as e:
        print(f"[-] Handshake failed during token harvest: {e}")
    finally:
        driver.quit()

def query_database(query_str):
    """Hits the backend API using the in-memory authenticated session."""
    global last_auth_time
    
    # Proactive refresh check if tokens are nearing lifetime expiration
    if time.time() - last_auth_time > AUTH_LIFETIME:
        refresh_tokens()
        
    query_words = query_str.split()
    required_words = [re.compile(r'\b' + re.escape(w) + r'\b', re.IGNORECASE) for w in query_words]
    
    try:
        response = session.post(
            "https://130point.com/api/search-live",
            headers={
                'Referer': 'https://130point.com/search',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
                'Content-Type': 'application/json',
            },
            json={"query": query_str, "sort": "EndTimeSoonest", "mp": "all", "tz": "America/Phoenix"},
            timeout=10
        )
        
        # Reactive refresh loop: if Cloudflare dropped the session early, recover immediately
        if response.status_code == 403:
            print("[!] Token expired early (403). Forcing immediate re-authentication...")
            refresh_tokens()
            return query_database(query_str)
            
        if response.status_code != 200:
            return f"Server rejected request with status code: {response.status_code}\n"
            
        data = response.json()
    except Exception as e:
        return f"Error communicating with 130Point API database: {e}\n"

    all_results = []
    for merchant, listings in data.get("results", {}).items():
        if isinstance(listings, list):
            all_results.extend(listings)

    filtered = [
        r for r in all_results
        if r.get("title")
        and all(w.search(r["title"]) for w in required_words)
        and not EXCLUDED_KEYWORDS.search(r["title"])
        and r.get("merchant") == "ebay"
        and int(r.get("bids", 0)) > 0
    ]

    # Generate the terminal display layout string
    output = f"\nQuery: {query_str}\n"
    output += f"Matched {len(filtered)} listings:\n\n"
    for r in filtered:
        url_path = r.get("link", "")
        full_url = f"https://www.ebay.com{url_path}" if url_path.startswith("/") else url_path
        clean_url = full_url.split("?")[0]
        output += f"  ${r['price']:>8} | {r.get('bids', 0):>2} bids | {r['title'][:60]:<60} | [{clean_url}]\n"

    prices = []
    for r in filtered:
        if r.get("price"):
            clean_price = str(r["price"]).replace("$", "").replace(",", "").strip()
            try:
                prices.append(float(clean_price))
            except ValueError:
                continue

    if prices:
        avg = sum(prices) / len(prices)
        output += f"\nAverage raw sold price: ${avg:.2f} ({len(prices)} listings)\n"
    else:
        output += f"\nNo matching raw sold listings found\n"
        
    return output

class PricingAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == '/search':
            query_params = parse_qs(parsed_url.query)
            q = query_params.get('q', [''])[0].strip()
            
            if not q:
                self.send_response(400)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Missing 'q' query parameter.\n")
                return
                
            print(f"[*] Processing socket query: {q}")
            result_output = query_database(q)
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(result_output.encode('utf-8'))
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Not Found. Use /search?q=query\n")

    def log_message(self, format, *args):
        # Mute standard http logging to preserve clean console data formatting
        return

if __name__ == '__main__':
    # Harvest tokens right at startup before starting the loop listener
    refresh_tokens()
    
    server = HTTPServer(('127.0.0.1', PORT), PricingAPIHandler)
    print(f"\n[+] Pricing socket listening locally on http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[-] Shutting down server socket.")
        server.server_close()
