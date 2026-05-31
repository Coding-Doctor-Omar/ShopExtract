from wreq.exceptions import DecodingError, TimeoutError, StatusError, BuilderError
from wreq import Client, Emulation, Response
from collections.abc import AsyncGenerator
from datetime import timedelta
from asyncio import Semaphore
from functools import wraps
import pandas as pd
import asyncio
import random
import json
import time
import csv
import sys
import re
import os

LOGO = r"""
   _____ _                 ______      _                  _   
  / ____| |               |  ____|    | |                | |  
 | (___ | |__   ___  _ __ | |__  __  _| |_ _ __ __ _  ___| |_ 
  \___ \| '_ \ / _ \| '_ \|  __| \ \/ / __| '__/ _` |/ __| __|
  ____) | | | | (_) | |_) | |____ >  <| |_| | | (_| | (__| |_ 
 |_____/|_| |_|\___/| .__/|______/_/\_\\__|_|  \__,_|\___|\__|
                    | |                                       
                    |_|                                                  
"""

MENU_OPTIONS = """
***************************
*        MAIN MENU        *
***************************
* 1. Generate Shopify CSV *
* 2. About                *
* 3. Exit                 *
***************************
"""

def limit_concurrency(limit: int):
    """Limits the number of concurrent coroutines."""

    SCRAPING_LIMIT = Semaphore(limit)
    
    def decorator(scrape_func):
        @wraps(scrape_func)
        async def wrapper(*args, **kwargs):
            async with SCRAPING_LIMIT:
                return await scrape_func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def clear_screen() -> None:
    """Clears the screen in the console for better UX."""

    if os.name == "nt": # Windows OS
        os.system("cls")
    else: # MacOS or Linux
        os.system("clear")

def elapsed_time(since: float) -> int:
    """Returns the elapsed time in seconds since a given start time in seconds.
    Args:
        since: A timestamp in seconds, representing the start time (e.g. time.perf_counter())."""

    current_time = time.perf_counter()
    time_elapsed = round(current_time - since)
    return time_elapsed

def create_empty_csv(name: str) -> None:
    """Generates an empty CSV with the required Shopify header row.
    Args:
        name: The name of the output CSV file."""

    with open(f"{name}.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header_row = [
            "Handle",
            "Title",
            "Body (HTML)",
            "Vendor",
            "Product Category",
            "Type",
            "Tags",
            "Published",
            "Option1 Name",
            "Option1 Value",
            "Option2 Name",
            "Option2 Value",
            "Option3 Name",
            "Option3 Value",
            "Variant SKU",
            "Variant Price",
            "Variant Compare At Price",
            "Image Src",
            "Image Alt Text",
            "Variant Image",
            "Variant Weight",
            "Variant Inventory Qty",
            "Variant Barcode"
        ]
        writer.writerow(header_row)

def generate_csvs(name: str) -> None:
    """Generates CSV files with the scraped data from a Shopify store.
    Args:
        name: The name of the output CSV file."""

    current_csv_rows = 1
    current_csv_num = 1
    with open(f"{name}_{current_csv_num}.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header_row = [
            "Handle",
            "Title",
            "Body (HTML)",
            "Vendor",
            "Product Category",
            "Type",
            "Tags",
            "Published",
            "Option1 Name",
            "Option1 Value",
            "Option2 Name",
            "Option2 Value",
            "Option3 Name",
            "Option3 Value",
            "Variant SKU",
            "Variant Price",
            "Variant Compare At Price",
            "Image Src",
            "Image Alt Text",
            "Variant Image",
            "Variant Weight",
            "Variant Inventory Qty",
            "Variant Barcode"
        ]
        writer.writerow(header_row)

    # Stream read from the jsonl file that contains the scraped data.
    with open(f"{name}.jsonl", mode="r", encoding="utf-8") as jsonl_file:
        for line in jsonl_file:
            product: dict = json.loads(line.strip()) # Convert each line in the jsonl file into a Python dict

            # Ensure the CSV does not exceed the 15 MB size limit or the 50,000 row limit for Shopify import.
            # If it reached near the limit, create a new CSV.
            if current_csv_rows > 40_000 or current_csv_rows + len(product["other_variants"]) + len(product["other_product_images"]) > 40_000:
                current_csv_num += 1
                current_csv_rows = 1
                create_empty_csv(f"{name}_{current_csv_num}")
            
            product_rows = [
                {key: val for key, val in product.items() if key not in ["other_variants", "other_product_images"]},
                *product["other_variants"],
                *product["other_product_images"]
            ]
            pd.DataFrame(product_rows).to_csv(f"{name}_{current_csv_num}.csv", mode="a", encoding="utf-8", index=False, header=False)
            current_csv_rows += ((len(product["other_variants"]) + len(product["other_product_images"])) + 1)

def parse_product(product: dict) -> dict:
    """Produces Shopify-import-CSV-compatible product data from any raw product data given.
    Args:
        product: A dictionary of raw product data obtained from the public Shopify API."""

    parsed_product = {
        "Handle": "",
        "Title": "",
        "Body (HTML)": "",
        "Vendor": "",
        "Product Category": "",
        "Type": "",
        "Tags": "",
        "Published": True,
        "Option1 Name": "",
        "Option1 Value": "",
        "Option2 Name": "",
        "Option2 Value": "",
        "Option3 Name": "",
        "Option3 Value": "",
        "Variant SKU": "",
        "Variant Price": "",
        "Variant Compare At Price": "",
        "Image Src": "",
        "Image Alt Text": "",
        "Variant Image": "",
        "Variant Weight": 0,
        "Variant Inventory Qty": 0,
        "Variant Barcode": "",
        "other_variants": [],
        "other_product_images": []
    }

    parsed_product["Handle"] = product["handle"]
    parsed_product["Title"] = product["title"]
    parsed_product["Body (HTML)"] = product.get("body_html", "")
    parsed_product["Vendor"] = product["vendor"]
    parsed_product["Product Category"] = ""
    parsed_product["Type"] = product.get("product_type", "")
    parsed_product["Tags"] = f'"{', '.join(product['tags'])}"'
    parsed_product["Published"] = True
    main_images = [image["src"] for image in product["images"]]
    
    for optin_num, optn in enumerate(product["options"], 1):
        parsed_product[f"Option{optin_num} Name"] = optn["name"]
    
    variants = product["variants"]

    parsed_product["Option1 Value"] = variants[0]["option1"]
    parsed_product["Option2 Value"] = variants[0]["option2"]
    parsed_product["Option3 Value"] = variants[0]["option3"]
    parsed_product["Variant SKU"] = variants[0].get("sku", "")
    parsed_product["Variant Price"] = variants[0]["price"]
    parsed_product["Variant Compare At Price"] = variants[0].get("compare_at_price", "")
    parsed_product["Image Src"] = main_images[0] if main_images else ""
    parsed_product["Image Alt Text"] = ""
    parsed_product["Variant Image"] = main_images[0] if main_images else ""
    parsed_product["Variant Weight"] = variants[0].get("grams", 0)

    if variants[0]["available"]:
        parsed_product["Variant Inventory Qty"] = 1
    else:
        parsed_product["Variant Inventory Qty"] = 0
    


    for variant in variants[1:]:        
        variant_data = {
            "Handle": parsed_product["Handle"],
            "Title": "",
            "Body (HTML)": "",
            "Vendor": "",
            "Product Category": "",
            "Type": "",
            "Tags": "",
            "Published": True,
            "Option1 Name": parsed_product["Option1 Name"],
            "Option1 Value": "",
            "Option2 Name": parsed_product["Option2 Name"],
            "Option2 Value": "",
            "Option3 Name": parsed_product["Option3 Name"],
            "Option3 Value": "",
            "Variant SKU": "",
            "Variant Price": "",
            "Variant Compare At Price": "",
            "Image Src": "",
            "Image Alt Text": "",
            "Variant Image": "",
            "Variant Weight": 0,
            "Variant Inventory Qty": 0,
            "Variant Barcode": ""
        }
        
        variant_data["Option1 Value"] = variant["option1"]
        variant_data["Option2 Value"] = variant["option2"]
        variant_data["Option3 Value"] = variant["option3"]

        variant_data["Variant SKU"] = variant.get("sku", "")
        variant_data["Variant Price"] = variant["price"]
        variant_data["Variant Compare At Price"] = variant.get("compare_at_price", "")

        try:
            variant_data["Variant Image"] = variant.get("featured_image", {}).get("src", "")
        except AttributeError:
            pass
        
        variant_data["Variant Weight"] = variant.get("grams", 0)

        if variant["available"]:
            variant_data["Variant Inventory Qty"] = 1
        else:
            variant_data["Variant Inventory Qty"] = 0
        


        parsed_product["other_variants"].append(variant_data)
    
    for image in product["images"]:
        if not image["variant_ids"] and image["src"] != parsed_product["Image Src"]:
            parsed_product["other_product_images"].append(
                {
                    "Handle": parsed_product["Handle"],
                    "Title": "",
                    "Body (HTML)": "",
                    "Vendor": "",
                    "Product Category": "",
                    "Type": "",
                    "Tags": "",
                    "Published": "",
                    "Option1 Name": "",
                    "Option1 Value": "",
                    "Option2 Name": "",
                    "Option2 Value": "",
                    "Option3 Name": "",
                    "Option3 Value": "",
                    "Variant SKU": "",
                    "Variant Price": "",
                    "Variant Compare At Price": "",
                    "Image Src": image["src"],
                    "Image Alt Text": "",
                    "Variant Image": "",
                    "Variant Weight": "",
                    "Variant Inventory Qty": "",
                    "Variant Barcode": ""
                }
            )
    
    return parsed_product

async def get_total_products_count(scrape_url: str, client: Client) -> int:
    """Gets the total number of products in the Shopify store. Returns 25001 for stores with more than 25k products.
    Args:
        scrape_url: The URL of the working /products.json endpoint of the Shopify store.
        client: A reference of the main scraping client."""

    delay_time = 1
    max_attempts = 10

    for attempt in range(1, max_attempts + 1):
        try:
            res: Response = await client.get(scrape_url.replace("/products.json", "/meta.json"))
            res.raise_for_status()
            data = await res.json()
        except (StatusError, DecodingError, TimeoutError):
            if attempt == 10:
                raise
            
            sleep_time = min(delay_time * 2 ** attempt + random.uniform(0.1, 2), 45) # Exponential back-off with a 45-second cap.
            await asyncio.sleep(sleep_time)
        else:
            break
    
    total_products = data["published_products_count"]
    
    return total_products

@limit_concurrency(limit=30)
async def get_page_products(scrape_url: str, page: int, client: Client) -> list:
    """Returns raw product data from any given API page.
    Args:
        scrape_url: The specific API url (e.g. https://some-store.myshopify.com/products.json).
        page: The pagination API query paramater.
        client: A reference of the main scraping client."""

    delay_time = 1
    max_attempts = 10
    parameters = {"page": page, "limit": 250}

    await asyncio.sleep(random.uniform(0.1, 1.5)) # Random small jitter

    for attempt in range(1, max_attempts + 1):
        try:
            res: Response = await client.get(scrape_url, query=parameters)
            res.raise_for_status()
            data = await res.json()
        except (StatusError, DecodingError, TimeoutError):
            if attempt == 10:
                raise
            
            sleep_time = min(delay_time * 2 ** attempt + random.uniform(0.1, 2), 45) # Exponential back-off with a 45-second cap.
            await asyncio.sleep(sleep_time)
        else:
            break

    
    return data["products"]

async def get_endpoint_products(scrape_info: dict, client: Client) -> AsyncGenerator[dict, None, None]:
    """Scrapes all available products from a given endpoint.
    Args:
        scrape_info: A dictionary containing necessary info such as the url of the endpoint, total products count of the store.
        client: A reference of the main scraping client."""

    scrape_url = scrape_info["url"]
    total_products = scrape_info["total_products"]
    
    num_pages = total_products // 250 + (1 if total_products % 250 > 0 else 0)


    tasks = [get_page_products(scrape_url, page_num, client) for page_num in range(1, num_pages + 1 if num_pages <= 100 else 101)]
    for future in asyncio.as_completed(tasks):
        for product in await future:
            yield parse_product(product)

def get_collection_page_tasks(collection: dict, client: Client) -> list:
    """Returns a list of get_page_products() coroutines for a given collection.
    Args:
        collection: A dictionary containing collection information.
        client: A reference of the main scraping client."""
    
    num_pages = collection["products_count"] // 250 + (1 if collection["products_count"] % 250 > 0 else 0)
    tasks = [get_page_products(collection["url"], page_num, client) for page_num in range(1, num_pages + 1 if num_pages <= 100 else 101)]

    return tasks

    
async def get_collections(scrape_url: str, client: Client) -> list:
    """Returns a list of all collections in the store with at least one listed product.
    Args:
        scrape_url: The URL of the valid /products.json endpoint of the store.
        client: A reference of the main scraping client."""
    
    parameters = {
        "page": 1,
        "limit": 250
    }
    collections_url = scrape_url.replace("/products.json", "/collections.json")

    collections_data = []
    delay_time = 1
    max_attempts = 10
    
    while parameters["page"] <= 100:
        for attempt in range(1, max_attempts + 1):
            try:
                res: Response = await client.get(collections_url, query=parameters)
                res.raise_for_status()
                data = await res.json()
            except (StatusError, DecodingError, TimeoutError):
                if attempt == 10:
                    raise
                
                sleep_time = min(delay_time * 2 ** attempt + random.uniform(0.1, 2), 45)
                await asyncio.sleep(sleep_time)
            else:
                break

        
        collections = data["collections"]

        if not collections:
            break

        for collection in collections:
            if collection["handle"] not in [c["url"].split("/")[-1].split(".json")[0] for c in collections_data] and collection["products_count"] > 0:
                collections_data.append(
                    {
                        "url": collections_url.split("/collections.json")[0] + f"/collections/{collection["handle"]}/products.json",
                        "products_count": collection["products_count"]
                    }
                )
        
        parameters["page"] += 1
        await asyncio.sleep(0.3)
    
    return collections_data



async def get_scrape_url(store_url: str, client: Client) -> str:
    """Returns the valid /products.json URL of a Shopify store.
    Args:
        store_url: The normal user-facing URL of the Shopify store.
        client: A reference of the main scraping client."""

    base_url = "https://" + store_url.split("//")[-1].split("/")[0].split("?")[0]
    products_endpoint = base_url + "/products.json"

    try:
        res = await client.get(products_endpoint)
        res.raise_for_status()
        data = await res.json()
    except StatusError:
        products_endpoint = None
    except Exception:
        products_endpoint = None
    else:
        if "products" in data:
            return products_endpoint
        else:
            products_endpoint = None
    
    if not products_endpoint:
        try:
            res = await client.get(base_url)

            # Use regex to find the <STORE>.myshopify.com/products.json URL of the Shopify store in case the normal /products.json is blocked.
            public_store_name = list(set(re.findall(pattern=r'\b([a-zA-Z0-9-]+)\.myshopify\.com\b', string=await res.text())))[0]
        except IndexError:
            return ""
        except Exception:
            return ""
        else:
            return f"https://{public_store_name}.myshopify.com/products.json"


async def initiate_scraping_operation(store_url: str, output_csv_name: str="shopify") -> None:
    """The main scraping function.
    Args:
        store_url: The normal user-facing URL of the Shopify store.
        output_csv_name: The user's desired name for the output CSV file."""
    
    scrape_count = 0
    scraped_handles = set()

    if not output_csv_name:
        output_csv_name = "shopify"
    
    scraping_client = Client(emulation=Emulation.Chrome147, cookie_store=True, timeout=timedelta(seconds=10))
    
    print(f"Initializing scraping operation...\n")
    scrape_url = await get_scrape_url(store_url=store_url, client=scraping_client)

    try:
        total_products = await get_total_products_count(scrape_url=scrape_url, client=scraping_client)
    except BuilderError:
        input(f"Failed to find any 'myshopify.com' public domain for {store_url}.\n\nPress ENTER to go to the main menu.")
        return
    
    
    # Implement the /products.json strategy for shops with less than or equal to 25,000 products.
    if total_products <= 25_000:
        scraping_info = {
            "url": scrape_url,
            "total_products": total_products,
        }

        with open(f"{output_csv_name}.jsonl", mode="w", newline="", encoding="utf-8") as jsonl_file:
            start_time = time.perf_counter()
            async for product in get_endpoint_products(scraping_info, scraping_client):
                if product["Handle"] not in scraped_handles:
                    scraped_handles.add(product["Handle"])
                    jsonl_file.write(json.dumps(product) + "\n")
                    scrape_count += 1
                
                elapsed_secs = elapsed_time(since=start_time)
                elapsed_secs_display = elapsed_secs % 60
                elapsed_mins = (elapsed_secs % 3600) // 60
                elapsed_hrs = elapsed_secs // 3600
                print(f"\rScrape Count: {scrape_count:,}/{total_products:,} | Elapsed Time: {elapsed_hrs:02}:{elapsed_mins:02}:{elapsed_secs_display:02}\033[K", end="", flush=True)

    else: # Implement the collections strategy for stores with more than 25,000 products.
        collections = await get_collections(scrape_url=scrape_url, client=scraping_client)
        start_time = time.perf_counter()

        with open(f"{output_csv_name}.jsonl", mode="w", newline="", encoding="utf-8") as jsonl_file:
            task_groups = [get_collection_page_tasks(collection={"url": collection["url"], "products_count": collection["products_count"]}, client=scraping_client) for collection in collections]
            tasks = [task for group in task_groups for task in group]

            
            for future in asyncio.as_completed(tasks):
                for raw_product in await future:
                    product = parse_product(raw_product)
                    
                    if product["Handle"] not in scraped_handles:
                        scraped_handles.add(product["Handle"])
                        jsonl_file.write(json.dumps(product) + "\n")
                        scrape_count += 1
                    
                    elapsed_secs = elapsed_time(since=start_time)
                    elapsed_secs_display = elapsed_secs % 60
                    elapsed_mins = (elapsed_secs % 3600) // 60
                    elapsed_hrs = elapsed_secs // 3600
                    print(f"\rScrape Count: {scrape_count:,} | Elapsed Time: {elapsed_hrs:02}:{elapsed_mins:02}:{elapsed_secs_display:02}\033[K", end="", flush=True)
                

            
    
    print(f"\n\nScraping Complete!\n")

    print(f"\nGenerating CSV(s)...\n")
    generate_csvs(name=output_csv_name)
    input("CSV Generated Successfully!\n\nPress ENTER to return to the main menu.")


async def main() -> None:
    """The main function that handles the entire scraper."""

    while True:
        clear_screen()
        print(f"{LOGO}")
        print(f"{MENU_OPTIONS}\n")

        try:
            user_choice = int(input("Choose an option: ").strip())
        except ValueError:
            input("Invalid option. Press ENTER to retry.")
            continue

        if user_choice == 3:
            sys.exit(0)
        
        if user_choice not in [1, 2]:
            input("Invalid option. Press ENTER to retry.")
            continue
        elif user_choice == 1:
            shopify_store_url = input("Store URL: ").strip().lower()
            output_name = input("Type a name for the output CSV: ").lower().strip().split(".")[0].replace("/", "").replace('\\', "").replace("+", "").replace("-", "").replace(" ", "_")
            clear_screen()
            print(f"{LOGO}\n")
            await initiate_scraping_operation(store_url=shopify_store_url, output_csv_name=output_name)
            continue
        elif user_choice == 2:
            clear_screen()
            print(f"{LOGO}\n")
            print("ShopExtract is your go-to tool for scraping ANY shopify store on the internet.")
            print("It reliably and quickly extracts the entire product catalog of any shopify store and generates Shopify-compatible, import-ready CSVs.")
            print("All you have to do is provide the Shopify store URL.")
            print("-------------------------------------------------------\n")
            print("Developed By: Dr. Omar Abdelhamid, a 5th-Year Medical Student at KasrAlainy Medical School as of 2026.")
            print("GitHub Profile: https://github.com/Coding-Doctor-Omar")
            print("LinkedIn Profile: https://www.linkedin.com/in/dr-omar-abdelhamid-37ab6b366/\n")
            input("Press ENTER to go back to the main menu.")
            continue
        


if __name__ == "__main__":
    asyncio.run(main())
