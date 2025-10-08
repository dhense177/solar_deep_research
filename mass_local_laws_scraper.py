from playwright.async_api import async_playwright
from crawl4ai import AsyncWebCrawler
import asyncio
import pandas as pd
import os
import random
import requests
import urllib.parse
from pathlib import Path

UNKNOWN_LINKS = []


async def download_file(url, filepath):
    """Download a file from URL to specified filepath"""
    try:
        print(f"📥 Downloading: {os.path.basename(filepath)}")
        
        # Use requests to download the file
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Write file to disk
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"✅ Downloaded: {os.path.basename(filepath)}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to download {url}: {e}")
        return False


async def is_pdf(url):
    """Check if URL is a PDF - handles redirects with Playwright"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            
            print(f"🔍 Checking: {url}")
            
            # Navigate to URL and follow redirects
            response = await page.goto(url, wait_until='networkidle', timeout=10000)
            
            # Get final URL after redirects
            final_url = page.url
            print(f"📍 Final URL: {final_url}")
            
            # Check if final URL ends with .pdf
            if final_url.lower().endswith('.pdf'):
                print("✅ PDF detected by URL extension")
                await browser.close()
                return True, final_url
            
            # Check response headers
            if response:
                content_type = response.headers.get('content-type', '').lower()
                print(f"📄 Content-Type: {content_type}")
                
                if 'application/pdf' in content_type:
                    print("✅ PDF detected by content-type")
                    await browser.close()
                    return True, final_url
            
            # Check page title for PDF indicators
            title = await page.title()
            if 'pdf' in title.lower():
                print("✅ PDF detected by page title")
                await browser.close()
                return True, final_url
            
            print("❌ Not a PDF")
            await browser.close()
            return False, final_url
            
    except Exception as e:
        print(f"Error checking {url}: {e}")
        return False, url



async def get_links():
    """Simple scraper for Massachusetts laws with dropdown selection"""
    # urls = [
    #     'https://www.mass.gov/info-details/cities-towns-starting-with-a-c-ordinances-bylaws',
    #     'https://www.mass.gov/info-details/cities-towns-starting-with-d-f-ordinances-bylaws',
    #     'https://www.mass.gov/info-details/cities-towns-starting-with-g-j-ordinances-bylaws',
    #     'https://www.mass.gov/info-details/cities-towns-starting-with-k-m-ordinances-bylaws',
    #     'https://www.mass.gov/info-details/cities-towns-starting-with-n-p-ordinances-bylaws',
    #     'https://www.mass.gov/info-details/cities-towns-starting-with-q-s-ordinances-bylaws',
    #     'https://www.mass.gov/info-details/cities-towns-starting-with-t-z-ordinances-bylaws'
    # ]
    url = 'https://www.mass.gov/info-details/cities-towns-starting-with-a-c-ordinances-bylaws'

    # subdirectory_path = os.path.join('./extracted_data/mass_municipalities', county, town)
    subdirectory_path = './extracted_data/mass_municipalities'
    os.makedirs(subdirectory_path, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Navigate to page
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        print(f"🌐 Loaded page: {url}")

        rich_text_divs = await page.query_selector_all("div.ma__rich-text div.ma__rich-text")
        print(f"📄 Found {len(rich_text_divs)} nested div elements with class 'ma__rich-text'")

        all_links = []
        
        # Loop through each div
        for i, div in enumerate(rich_text_divs):
            print(f"\n🔍 Processing div {i+1}/{len(rich_text_divs)}")
            
            # Find all <li> tags within this div
            li_elements = await div.query_selector_all("li")
            print(f"   Found {len(li_elements)} <li> elements")

            # li_elements = li_elements[:2]
            
            # Loop through each <li> element
            for j, li in enumerate(li_elements):
                # Get all links within this <li>
                links = await li.query_selector_all("a[href]")
                
                # Check if there are multiple links in this <li>
                if len(links) > 1:
                    print(f"      📋 Multiple links found in li {j+1}, looking for 'Zoning' link...")
                    
                    # Get the municipality name from <strong> tag
                    strong_element = await li.query_selector("strong")
                    municipality_name = ""
                    if strong_element:
                        municipality_name = await strong_element.inner_text()
                        municipality_name = municipality_name.rstrip(':')
                        print(f"      🏛️ Municipality: {municipality_name}")
                    
                    # Look for the "Zoning" link specifically
                    # zoning_link_found = False
                    d = {'municipality': municipality_name}
                    d['links'] = []
                    for link in links:
                        try:
                            href = await link.get_attribute("href")
                            text = await link.inner_text()

                            if href:
                                d['links'].append((text.strip().lower(), href))

                                
                        except Exception as e:
                            print(f"      ❌ Error processing links: {e}")
                    all_links.append(d)
                    # if not zoning_link_found:
                    #     print(f"      ⚠️ No 'Zoning' link found in li {j+1}")
                
                else:
                    # Single link - process normally
                    for link in links:
                        try:
                            href = await link.get_attribute("href")
                            municipality_name = await link.inner_text()
                            
                            if href:
                                d = {
                                    'municipality': municipality_name,
                                    'links': [('single', href)]
                                }
                                # all_links.append((href, 'Single', municipality_name))

                                
                        except Exception as e:
                            print(f"      ❌ Error processing link: {e}")
                    all_links.append(d)
        
        await browser.close()
        
        return all_links

def find_document_type(href):
    if 'ecode360' in href.lower():
        return 'ecode360'
    elif 'documentcenter' in href.lower():
        return 'documentcenter'
    elif href.lower().endswith('.pdf'):
        return 'pdf'
    else:
        return 'unknown'

async def download_ecode360_file(href, municipality_name):
    global downloaded
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            
            # Set up download handling
            download_path = './extracted_data/mass_municipalities'
            os.makedirs(download_path, exist_ok=True)
            
            # Listen for download events
            download_info = None
            
            def handle_download(download):
                nonlocal download_info
                download_info = download
                print(f"      📥 Download started: {download.suggested_filename}")
            
            page.on("download", handle_download)
            
            print(f"      🔗 ecode360 link found: {href}")
            await page.goto(href, timeout=30000)
            await page.wait_for_load_state("networkidle")
            print(f"🌐 Loaded page: {href}")

            # Look for download button and click it
            try:
                download_button = await page.query_selector("#downloadButton")
                if download_button:
                    print(f"      📥 Found download button, clicking...")
                    await download_button.click()
                    await page.wait_for_timeout(2000)  # Wait for popup to appear
                    
                    # Look for PDF download icon in popup
                    pdf_download_icon = await page.query_selector("#pdfDownload")
                    if pdf_download_icon:
                        print(f"      📄 Found PDF download icon in popup, clicking...")
                        await pdf_download_icon.click()
                        await page.wait_for_timeout(20000)  # Wait for download to start
                        
                        # Wait for download to complete
                        if download_info:
                            filename = f"{municipality_name.lower()}_ecode360.pdf"
                            filepath = os.path.join(download_path, filename)
                            await download_info.save_as(filepath)
                            print(f"      ✅ File downloaded: {filepath}")
                            downloaded = True
                        else:
                            print(f"      ⚠️ No download event detected")
                    else:
                        print(f"      ⚠️ No PDF download icon found in popup")
                else:
                    print(f"      ⚠️ No download button found on ecode360 page")
            except Exception as e:
                print(f"      ❌ Error clicking download button: {e}")
            
            await browser.close()
    except Exception as e:
        print(f"      ❌ Error in download_ecode360_file: {e}")
        downloaded = False

async def download_documentcenter_file(href, municipality_name):
    global downloaded
    try:
        print(f"      🔗 documentcenter link found: {href}")
        filename = f"{municipality_name.lower()}_documentcenter.pdf"
        filepath = os.path.join('./extracted_data/mass_municipalities', filename)
        await download_file(href, filepath)
        downloaded = True
    except Exception as e:
        print(f"      ❌ Error downloading documentcenter file: {e}")
        downloaded = False

async def download_pdf_file(href, municipality_name):
    global downloaded
    try:
        filename = f"{municipality_name.lower()}.pdf"
        filepath = os.path.join('./extracted_data/mass_municipalities', filename)
        await download_file(href, filepath)
        downloaded = True
    except Exception as e:
        print(f"      ❌ Error downloading PDF file: {e}")
        downloaded = False


async def main():
    
    DOWNLOAD_FUNCTIONS = {
        'ecode360': download_ecode360_file,
        'documentcenter': download_documentcenter_file,
        'pdf': download_pdf_file
    }
    links = await get_links()

    print(links)

    links = links[17:]

    for link in links:

        global downloaded
        downloaded = False

        if link['links'][0][0] == 'single':
            document_type = find_document_type(link['links'][0][1])
            # Call function based on returned document type
            if document_type == 'unknown':
                continue
            else:
                await DOWNLOAD_FUNCTIONS[document_type](link['links'][0][1], link['municipality'])
        else:
            # Reverse sort the links
            link['links'].reverse()

            for l in link['links']:
                if l[0] == 'zoning':
                    document_type = find_document_type(l[1])
                    if document_type == 'unknown':
                        continue
                    else:
                        await DOWNLOAD_FUNCTIONS[document_type](l[1], link['municipality'])
                        break
                elif l[0] == 'general':
                    document_type = find_document_type(l[1])
                    if document_type == 'unknown':
                        continue
                    else:
                        await DOWNLOAD_FUNCTIONS[document_type](l[1], link['municipality'])
                        break
                else:
                    continue

        if not downloaded:
            UNKNOWN_LINKS.append(link)


if __name__ == "__main__":
    asyncio.run(main())