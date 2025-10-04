""" Script that downloads the FAA's list of ICAO airline codes and formats it
into a series of lookup tables separated by letter for use with FlightGazer or any other python program.
Can be used to update the database in the future.
To see changes on the FAA's side: https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap0_cam.html """
# by WeegeeNumbuh1
# Last updated: September 2025
# Released in conjunction with Flightgazer version: v.8.3.0

if __name__ != '__main__':
    print("This script cannot be imported as a module.")
    print("Run this directly from the command line.")
    raise SystemExit

try:
    import requests
except ImportError:
    print("This script requires the 'requests' module.")
    print("You can install it using 'pip install requests'.")
    raise SystemExit
try:
    from bs4 import BeautifulSoup as bs
except ImportError:
    print("This script requires the 'beautifulsoup4' module.")
    print("You can install it using 'pip install beautifulsoup4'.")
    raise SystemExit
try:
    from fake_useragent import UserAgent
except ImportError:
    print("This script requires the 'fake_useragent' module.")
    print("You can install it using 'pip install fake_useragent'.")
    raise SystemExit

from pathlib import Path
import datetime
import unicodedata

current_path = Path(__file__).resolve().parent
write_path = Path(f"{current_path}/operators.py")
alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
header_str = """\"\"\" Importable python module for aviation callsign lookup.
All data sourced from the Federal Aviation Administration, Directive No. JO 7340.2N, Chapter 3, Section 3
along with Wikipedia (https://en.wikipedia.org/wiki/List_of_airline_codes) for the operators' friendly names.
The accuracy of the 'friendly names' for the operators is dependent on what is pulled from Wikipedia at the time
this file was generated, so your mileage may vary.
When comparing which version of the Directive was used, check the generation timestamp below
with the release schedule in Section 1-1-6 (https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap1_section_1.html).
If you plan to use this module in other projects, please reference the original project:
https://github.com/WeegeeNumbuh1/FlightGazer \"\"\"\n\n"""
user = UserAgent(browsers='Chrome')
HTML_header = {'User-Agent': str(user.random)}

def dict_lookup(list_of_dicts: list, key: str, search_term: str) -> dict | None:
    """ Function pulled directly from FlightGazer """
    if not search_term:
        return None
    try:
        for dict_ in [x for x in list_of_dicts if x.get(key) == search_term]:
            return dict_
        return None
    except Exception:
        return None

def strip_accents(s: str) -> str:
   """ https://stackoverflow.com/a/518232 """
   return ''.join(c for c in unicodedata.normalize('NFD', s)
                  if unicodedata.category(c) != 'Mn')

print("Downloading data from the FAA...")
dataset = requests.get('https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap3_section_3.html', headers=HTML_header, timeout=5)
dataset.raise_for_status()
html = dataset.text
print("Downloading supplementary info from Wikipedia...")
dataset2 = dataset = requests.get('https://en.wikipedia.org/wiki/List_of_airline_codes', headers=HTML_header, timeout=5)
dataset2.raise_for_status()
html2 = dataset2.text
print("Parsing HTML... (this will take a few seconds)")
soup = bs(html, 'html.parser')
soup2 = bs(html2, 'html.parser')
data = []
data2 = []
print("Sorting data...")
tables = soup2.find_all('table')
for table in tables:
    headers = [th.get_text(strip=True, separator=" ") for th in table.find_all('th')]
    for row in table.find_all('tr'):
        cells = [td.get_text(strip=True, separator=" ") for td in row.find_all('td')]
        if cells:
            data2.append({k:v for k,v in zip(headers, cells)})
        # keys are IATA, ICAO, Airline, Call sign, Country/Region, Comments
for i, entry in enumerate(data2):
    # for telephony comparison
    if entry.get('Call sign', ''):
        data2[i]['Call sign'] = entry['Call sign'].strip().upper()
entries_to_ignore_contains = [
    'efunct', # Defunct
    'ormerly', # Formerly
    'no longer allocated'
]
print(f"Sorted {len(data2)} rows from Wikipedia.")

# if write_path.exists():
#     print(f"File '{write_path}' already exists.\nBacking it up as '{write_path}.old'...")
#     write_path.rename(f"{write_path}.old")

print(f"Writing to {write_path}...")
datenow = datetime.datetime.now()

with open(write_path, 'w', encoding='utf-8') as file:
    file.write(header_str)
    file.write(f"# Generated on: {datenow.strftime('%Y-%m-%d %H:%M:%S')}\n")
    for i, table in enumerate(soup.find_all('table')):
        rows = table.find_all('tr')
        file.write(f"{alphabet[i]}_TABLE = [\n")
        letter_section = []
        for j, row in enumerate(rows):
            cols = row.find_all('td')
            if len(cols) > 0:
                if (matching_entry := dict_lookup(data2, 'ICAO', cols[0].text.strip().upper())) is not None:
                    if (matching_callsign := dict_lookup(data2, 'Call sign', cols[3].text.strip().upper())) is not None:
                        friendly = strip_accents(matching_callsign.get('Airline', ''))
                        comment = matching_callsign.get('Comments', '')
                    else:
                        friendly = strip_accents(matching_entry.get('Airline', ''))
                        comment = matching_entry.get('Comments', '')
                    if any(substring in comment for substring in entries_to_ignore_contains):
                        friendly = ''
                        comment = ''
                    if cols[2].text.strip() != matching_entry.get('Country/Region', '').upper():
                        friendly = ''
                        comment = ''
                else:
                    friendly = ''
                    comment = ''
                letter_section.append({
                    '3Ltr': cols[0].text.strip(),
                    'Company': cols[1].text.strip(),
                    'Country': cols[2].text.strip(),
                    'Telephony': cols[3].text.strip(),
                    'FriendlyName': friendly,
                    'Comments': comment
                })
                file.write(f"    {letter_section[-1]},\n")
        file.write(f"] # {j} entries.\n\n")
        data.extend(letter_section)
        print(f"Wrote table '{alphabet[i]}' with {j} entries.")
    file.write(f"# {len(data)} entries in total.\n")

print(f"A total of {len(data)} entries were written.")
print(f"Resulting file size: {(write_path.stat().st_size) / (1024):.3f} KiB.")
print("\nDone.")