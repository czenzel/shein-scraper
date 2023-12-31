from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from lxml import etree
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
from pymongo import MongoClient
from datetime import datetime
import json
import time
import os
import math

from functions.getProxy import *
from functions.getUserAgent import *

#proxy = getProxy()

limit_to_3_max_review_pages = False
RETRIES = 3
mongo_host = os.environ.get('MONGO_HOST', 'localhost')
client = MongoClient(f'mongodb://{mongo_host}:27017/')
db = client['shein']
url_collection = db['product_urls']
product_collection = db['products']
product_reviews_collection = db['product_reviews']

if limit_to_3_max_review_pages:
    print('Limiting to 3 max review pages per product ACTIVATED')

# Setup Index
try:
    product_collection.create_index('title', text_index=True)
except Exception as e:
    print('Title index already exists')
    pass

try:
    product_collection.create_index('url', unique=True)
except Exception as e:
    print('URL index already exists')
    pass

try:
    product_collection.create_index('product_id', unique=True)
except Exception as e:
    print('Product ID index already exists')
    pass

#prox_options = {
#    'proxy': {
#        'http': proxy
#    }
#}

options = Options()
options.add_argument('--headless')
#options.add_argument('--no-sandbox')
#options.add_argument('--disable-dev-shm-usage')
options.add_argument('--user-agent=' + GET_UA())
options.add_argument('--incognito')
options.add_argument('--ignore-certificate-errors')
options.add_argument('--ignore-ssl-errors')
options.binary_location = '/usr/bin/google-chrome'
chrome_drvier_binary = '/usr/bin/chromedriver'
driver = webdriver.Chrome(service=Service(chrome_drvier_binary), options=options)

pending_urls = url_collection.find({"status": "pending"}).sort("timestamp", 1)

def wait_for_review_image_load(driver, image_element, timeout=15):
    WebDriverWait(driver, timeout).until_not(lambda d: 'sheinsz.ltwebstatic.com' in image_element.get_attribute('src'))

for url in pending_urls:
    url = url['url']
    print('Processing ' + url)

    retries = 0
    while retries < RETRIES:
        try:
            url_collection.update_one({'url': url}, {'$set': {'status': 'processing'}})
            driver.get(url)
            #WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[1]/div/div[1]/div/div[2]/div[2]/div/div[3]/div[1]/div/div/button[2]/div')))
            break
        except Exception as e:
            print('Scraping error: ' + str(e))
            retries += 1
            print(f'Retrying ({retries} of {RETRIES})')

    if retries == RETRIES:
        print('Giving up on ' + url)
        url_collection.update_one({'url': url}, {'$set': {'status': 'failed'}})
        continue
    
    try:
        print('Processing ' + url)
        try: # Close the popup
            button_popup = driver.find_element(By.XPATH, '/html/body/div[1]/div[2]/div/div/div[1]/div/div/div[2]/div/i').click()
            driver.implicitly_wait(5)
            ActionChains(driver).move_to_element(button_popup).click(button_popup).perform()
        except Exception as e:
            pass
        try: # Accept cookies
            button_cookies = driver.find_element(By.ID, 'onetrust-accept-btn-handler').click()
            driver.implicitly_wait(5)
            ActionChains(driver).move_to_element(button_cookies).click(button_cookies).perform()
        except Exception as e:
            pass

        single_product_data = []
        product_id = driver.find_element(By.CLASS_NAME, 'product-intro__head-sku').text.replace('SKU: ', '')
        title = driver.find_element(By.CLASS_NAME, 'product-intro__head-name').text

        # get product images for every color
        product_images = []
        get_product_images = True

        try:
            colors = driver.find_elements(By.CLASS_NAME, 'product-intro__color-radio')
        except Exception as e:
            try:
                colors = driver.find_elements(By.CLASS_NAME, 'product-intro__color-block')
            except Exception as e:
                get_product_images = False
        product_colors = []
        if get_product_images:
            if len(colors) >= 2:
                for color in colors:
                    selected_color = color.get_attribute('aria-label')
                    print('Select Color: %s' % selected_color)
                    product_colors.append(selected_color)

                    ActionChains(driver).move_to_element(color).click(color).perform()
                    color.click()
                    time.sleep(5) # Wait for product iamges to appear
                    try:
                        product_cropped_images = driver.find_elements(By.CLASS_NAME, 'product-intro__thumbs-item')
                        for image in product_cropped_images:
                            image_url = image.find_element(By.TAG_NAME, 'img').get_attribute('src')
                            final_url = image_url.replace('_thumbnail_220x293', '')
                            print('Adding product image with color values %s' % final_url)
                            product_images.append([selected_color, final_url])
                    except Exception as e:
                        print('There was an error getting the product images for ' + product_id)
                        print('Product Image Error: ' + str(e))
                        continue

        product_data = {
            'product_id': product_id,
            'title': title,
            'url': url,
            'colors': product_colors,
            'images': product_images,
            'last_update': datetime.now(),
            'timestamp': datetime.now()
        }

        #Insert the product data into MongoDB
        product_collection.insert_one(product_data)

        # Get the reviews
        try:
            image_count = driver.find_element(By.CLASS_NAME, 'j-expose__review-image-tab-target').text
            image_count = re.sub("\D", "", image_count)
            image_count = int(image_count)
        except Exception as e:
            image_count = 0

        print(f'Found {image_count} reviews with images')
        if image_count > 0:
            try:
                # move to image button
                ActionChains(driver).move_to_element(driver.find_element(By.CLASS_NAME, 'j-expose__review-image-tab-target')).perform()
                image_tab_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, 'j-expose__review-image-tab-target'))) # Review with images tab
                ActionChains(driver).move_to_element(image_tab_btn).click(image_tab_btn).perform()
            except Exception as e:
                print('Error clicking image tab: ' + str(e))
                pass
            print('Clicked image tab button')
            image_pages = math.ceil(int(image_count) / 3) # 3 images per page
            print(f'Found {image_pages} pages of reviews with images')
            if limit_to_3_max_review_pages:
                image_pages = min(3, image_pages)
            for i in range(1, image_pages + 1): # Loop through all image pages
                print(f'Processing image page {i} of {image_pages}')  # Progress update

                page_reviews = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'common-reviews__list-item')))

                for review in page_reviews:
                    print('=== Review ===')
                    review_info = {}
                    try:
                        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'common-reviews__list-item')))
                        ActionChains(driver).move_to_element(review).perform() # Hover over review to load it
                    except Exception as e:
                        print('Error hovering over review')
                        pass

                    try:
                        review_info['review_id'] = int(review.get_attribute('data-comment-id'))
                    except Exception as e:
                        review_info['review_id'] = 0

                    print('Review ID: ' + str(review_info['review_id']))

                    try:
                        review_info['likes'] = int(re.sub("\D", "", review.find_element(By.CLASS_NAME, 'like-num').text))
                    except Exception as e:
                        review_info['likes'] = 0
                        pass

                    print('Likes: ' + str(review_info['likes']))

                    review_info['product_id'] = product_id
                    print('Product ID: ' + str(review_info['product_id']))
                    review_info['timestamp'] = datetime.now()
                    print('Timestamp: ' + str(review_info['timestamp']))

                    try:
                        print('Getting images for review ' + str(review_info['review_id']))
                        start_time = time.time()
                        while True:
                            images = review.find_elements(By.CLASS_NAME, 'j-review-img')
                            if images or time.time() - start_time > 10:
                                break
                            time.sleep(0.5)

                        if not images:
                            print('No images found after 10 seconds')
                        else:
                            print('Found ' + str(len(images)) + ' images')
                        image_array = []

                        for image in images:
                            try:
                                ActionChains(driver).move_to_element(image).perform() # Hover over image to load it
                                wait_for_review_image_load(driver, image)
                                image_url = image.get_attribute('src')
                                final_url = image_url.replace('_thumbnail_x460', '')
                                image_array.append('https:' + final_url)
                            except Exception as e:
                                pass


                        review_info['images'] = image_array
                    except Exception as e:
                        # Problem explanation:
                        # So when the first review has no images, the script tries to get the images of this review
                        # due the error "stale not found" the script will click on the image tab again
                        # and then it will try to get the new reviews from the right tab
                        print('There was an error getting the images / mostly because there are no images')
                        # click again on image tab
                        image_tab_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, 'j-expose__review-image-tab-target'))) # Review with images tab
                        ActionChains(driver).move_to_element(image_tab_btn).click(image_tab_btn).perform()
                        time.sleep(2)
                        continue

                    if review_info['review_id'] != 0 and review_info['likes'] != 0 and len(review_info['images']) > 0:
                        print('Inserting review into MongoDB')
                        product_reviews_collection.insert_one(review_info)
                        print('=====')
                    elif review_info['review_likes'] == 0:
                        print('Skipping all reviews because there are no likes anymore / which mostly means that the reviews doesnt show a human anymore')
                        print('=====')
                        pass
                    else:
                        print('Skipping review because it is missing data')
                        print('=====')

                if i < image_pages:
                    try:
                        next_page_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, 'sui-pagination__next')))
                        next_page_button.click()
                    except Exception as e:
                        print('Error clicking next page button: ' + str(e))
                        popover_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, 'sui-popover__content')))
                        popover_btn.click()
                        pass

                time.sleep(2)
        else:
            url_collection.update_one({'url': url}, {'$set': {'status': 'no_reviews'}})

    except Exception as e:
        print('General Error: ' + str(e))
        url_collection.update_one({'url': url}, {'$set': {'status': 'failed'}})
        continue
    
    
    url_collection.update_one({'url': url}, {'$set': {'status': 'complete'}})
    print('Done processing ' + url)
print('Done processing all URLs')
driver.quit()
client.close()