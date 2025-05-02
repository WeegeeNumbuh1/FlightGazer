''' Script that downloads the FAA's list of ICAO airline codes and formats it 
into a series of lookup tables separated by letter for use with FlightGazer or any other python program. 
Can be used to update the database in the future. '''
# by WeegeeNumbuh1

if __name__ != '__main__':
    print("This script cannot be imported as a module.")
    print("Run this directly from the command line.")
    raise SystemExit

try:
    import requests
except (ImportError, ModuleNotFoundError):
    print("This script requires the 'requests' module.")
    print("You can install it using 'pip install requests'.")
    raise SystemExit
try:
    from bs4 import BeautifulSoup as bs
except (ImportError, ModuleNotFoundError):
    print("This script requires the 'beautifulsoup4' module.")
    print("You can install it using 'pip install beautifulsoup4'.")
    raise SystemExit
from pathlib import Path
import datetime

current_path = Path(__file__).resolve().parent
write_path = Path(f"{current_path}/operators.py")
alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
header_str = """\'\'\' Importable python module for aviation callsign lookup.
All data sourced from the Federal Aviation Administration, Directive No. JO 7340.2N, Chapter 3, Section 3.
If you plan to use this module in other projects, please reference the original project:
https://github.com/WeegeeNumbuh1/FlightGazer \'\'\'\n\n"""

print("Downloading data from the FAA...")
dataset = requests.get('https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap3_section_3.html', timeout=5)
dataset.raise_for_status()
html = dataset.text
print("Parsing HTML... (this will take a few seconds)")
soup = bs(html, 'html.parser')
data = []
if write_path.exists():
    print(f"File '{write_path}' already exists. Backing it up as '{write_path}.old'...")
    write_path.rename(f"{write_path}.old")

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
                letter_section.append({
                    '3Ltr': cols[0].text.strip(),
                    'Company': cols[1].text.strip(),
                    'Country': cols[2].text.strip(),
                    'Telephony': cols[3].text.strip()
                })
                file.write(f"    {letter_section[-1]},\n")
        file.write(f"] # {j} entries.\n\n")
        data.extend(letter_section)
        print(f"Wrote table '{alphabet[i]}' with {j} entries.")
    file.write(f"# {len(data)} entries in total.\n")

print("\nDone.")