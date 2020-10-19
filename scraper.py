import pandas as pd
import time
import requests
from bs4 import BeautifulSoup
import json
import unicodecsv as csv
import re
import unicodedata
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def get_data(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html.parser')
    data = soup.findAll(text=True)

    # 'data' is a ResultSet but needs to be a string to parse as json
    full_string = ""
    for each in data:
        str(each)
        full_string += each

    parsed = json.loads(full_string)
    text = json.dumps(parsed, sort_keys=True, indent=4)
    return parsed

# return how many pages to iterate through
def get_last_page(parsed):
    last_page_json = parsed['links']['last']
    last_page = last_page_json.split('=')[1]
    return last_page

# scrape men or women's
def category_to_scrape(category):
    if category == 'Men':
        cat = 'https://shop.lululemon.com/api/c/men?page='
    elif category == 'Women':
        cat = 'https://shop.lululemon.com/api/c/women?page='
    return cat

def page_url_builder(category, page_num):
    front = category
    page_number = page_num
    end = '&pagesize=45'
    return (front + str(page_number) + end)

def scraper_to_df(category):
    cat = category_to_scrape(category)
    lulu = 'https://shop.lululemon.com'

    # scrape first page to get number of pages of products
    scrape_url = page_url_builder(cat, 1)
    print(scrape_url)
    parsed = get_data(scrape_url)
    last_page = get_last_page(parsed)

    temp_df = pd.DataFrame(columns = ['Category', 'Item Category', 'Display Name', 'Color', 'URL', 'Sale Price', 'Original Price', 'Sizes In Stock', 'Sizes OOS'] )

    # iterate through all pages
    for x in range(1, int(last_page) + 1):
        # already did page 1, don't want to request again
        if (x != 1):
            scrape_url = page_url_builder(cat, x)
            parsed = get_data(scrape_url)

        # number products on page
        num_products = len(parsed['data']['attributes']['main-content'][0]['records'])
        for y in range (0, num_products):
            try:
                # check to see if it's a sale product. if it isn't, just skip to next product
                sale_bool = int(parsed['data']['attributes']['main-content'][0]['records'][y]['product-on-sale'])
                if not sale_bool:
                    continue

                # other gender's products show up sometimes, but i want to bypass them so i am not making too many requests
                check_for_mens = parsed['data']['attributes']['main-content'][0]['records'][y]
                check_for_mens = str(check_for_mens)
                if category == 'Women':
                    if 'usmen' in check_for_mens:
                        continue
                    mf_cat = 'Womens'
                elif category == 'Men':
                    mf_cat = 'Men'

                type_clothing = parsed['data']['attributes']['main-content'][0]['records'][y]['default-parent-category']
                display_name = parsed['data']['attributes']['main-content'][0]['records'][y]['display-name']
                list_price = parsed['data']['attributes']['main-content'][0]['records'][y]['list-price']
                num_colors = len(parsed['data']['attributes']['main-content'][0]['records'][y]['sku-style-order'])

                prod_url = parsed['data']['attributes']['main-content'][0]['records'][y]['pdp-url']
                color_append_prod_url = '?color='

                for color_pos in range(0, num_colors):
                    try:
                        color = parsed['data']['attributes']['main-content'][0]['records'][y]['sku-style-order'][color_pos]['color-name']
                        color_id = parsed['data']['attributes']['main-content'][0]['records'][y]['sku-style-order'][color_pos]['color-id']
                        prod_color_url = lulu + prod_url + color_append_prod_url + color_id
                        # due to the way the website is set up, you have to add size to get the color's sale price
                        prod_color_url_size = prod_color_url + '&sz=4'
                        print(prod_color_url_size)

                        # need to request for the color's url to get price & size availability
                        r = requests.get(prod_color_url_size)
                        soup = BeautifulSoup(r.content, 'html.parser')

                        # get sale and original price
                        item_price = soup.find('span', {'class':'price-1SDQy price'})
                        sale_price_split = item_price.text.split()
                        sale_price = ''.join(sale_price_split[2:3])

                        orig_price = soup.find('span', {'class':'priceInactiveListPrice-182Wu price__inactive-list-price'}).text.split()
                        list_price = ''.join(orig_price[2:3])

                        # create and populate lists for size availability
                        instock = []
                        oos = []
                        for div in soup.findAll('div', {'class':'size-selector'}):
                            for i in soup.find_all('span', {'class':'sizeTile-3p7Pr'}):
                                if 'not available' not in i.text:
                                    instock.append(i.text)
                                else:
                                    parse_size = i.text
                                    unicode_normalize = unicodedata.normalize("NFKD", parse_size)
                                    size_only = unicode_normalize.replace(' (not available)', '')
                                    oos.append(size_only)

                        new_row = {'Category': mf_cat, 'Item Category': type_clothing, 'Display Name': display_name, 'Color': color, 'URL': prod_color_url, 'Sale Price': sale_price, 'Original Price': list_price, 'Sizes In Stock': str(instock).strip('[]'), 'Sizes OOS': str(oos).strip('[]')}
                        print(new_row)
                        temp_df = temp_df.append(new_row, ignore_index = True)
                    except:
                        break
            except:
                break
    return temp_df

def main():
    # initialize dataframe
    df  = pd.DataFrame(columns = ['Category', 'Item Category', 'Display Name', 'Color', 'URL', 'Sale Price', 'Original Price', 'Sizes In Stock', 'Sizes OOS'] )

    womens = scraper_to_df('Women')
    df = df.append(womens)
    mens = scraper_to_df('Men')
    df = df.append(mens)
    df.to_csv('luluwmtm.csv',index=False,header=True)

    # writes to google drive sheet, comment out the rest if running locally
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

    credentials = ServiceAccountCredentials.from_json_keyfile_name('client_secret.json', scope)
    client = gspread.authorize(credentials)

    spreadsheet = client.open('lulu-wmtm-scraper')

    with open('luluwmtm.csv', 'r', encoding='utf-8') as file_obj:
        content = file_obj.read()
        client.import_csv(spreadsheet.id, data=content.encode('utf-8'))


if __name__=="__main__":
    main()
