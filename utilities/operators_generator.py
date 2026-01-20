""" Script that downloads the FAA's list of ICAO airline codes and formats it
into a series of lookup tables separated by letter for use with FlightGazer or any other python program.
Can be used to update the database in the future.
To see changes on the FAA's side: https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap0_cam.html """
# by WeegeeNumbuh1
# Last updated: January 2026
# Released in conjunction with Flightgazer version: v.9.9.1

import sys

if __name__ != '__main__':
    print("This script cannot be imported as a module.")
    print("Run this directly from the command line.")
    sys.exit(1)

print("********** FlightGazer Operator Database Importer **********\n")

from time import perf_counter
script_start = perf_counter()
from pathlib import Path
import datetime

current_path = Path(__file__).resolve().parent
write_path = Path(current_path, 'operators.py')
alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

datenow = datetime.datetime.now(tz=datetime.timezone.utc)
old_version = None
old_version_time = None
if write_path.exists():
    print("Operators database exists, checking...")
    sys.path.append(current_path)
    try:
        import operators as op
        old_version = op.GENERATED
    except (ImportError, AttributeError) as e:
        # older version of the file
        search_line = '# Generated on:'
        old_version_raw = ''
        with open(write_path, 'r') as oldfile:
            for line in oldfile:
                if search_line in line:
                    old_version_raw = line.strip()
                    break
        if old_version_raw:
            # example string: '# Generated on: 2026-01-01 00:00:00'
            old_version = 'T'.join(old_version_raw.split()[3:]) + 'Z'
        else:
            print("Could not determine when this file was generated.")

    if old_version:
        try:
            old_version_time = datetime.datetime.strptime(
                old_version, "%Y-%m-%dT%H:%M:%S%z"
            )
            delta = datenow - old_version_time
            print(f"Current database was dated: {old_version_time}")
            print(f"({delta.days} day(s) ago)")
            if delta.days < 180:
                print("Database is still valid, no need to update.")
                print("\n***** Done. *****")
                sys.exit(0)
            else:
                print("Database is outdated.\n")
        except Exception as e:
            print(f"Could not determine when this file was generated.\n{e}")
    else:
        print("Could not determine when this file was generated.")

print("Continuing update...")
# load in all the other modules
import unicodedata
import gzip
import ast
import importlib
try:
    import requests
except ImportError:
    print("This script requires the 'requests' module.")
    print("You can install it using 'pip install requests'.")
    sys.exit(1)
try:
    from bs4 import BeautifulSoup as bs
except ImportError:
    print("This script requires the 'beautifulsoup4' module.")
    print("You can install it using 'pip install beautifulsoup4'.")
    sys.exit(1)
try:
    from fake_useragent import UserAgent
except ImportError:
    print("This script requires the 'fake_useragent' module.")
    print("You can install it using 'pip install fake-useragent'.")
    sys.exit(1)

FAA_source = 'https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap3_section_3.html'
tar1090db = 'https://github.com/wiedehopf/tar1090-db/raw/refs/heads/master/db/operators.js'
tar1090db_ver = 'https://raw.githubusercontent.com/wiedehopf/tar1090-db/refs/heads/master/version'
header_str = """\"\"\" Importable python module for aviation callsign lookup.
All data sourced from the Federal Aviation Administration, Directive No. JO 7340.2N, Chapter 3, Section 3.
For the operators' friendly names, tar1090-db (https://github.com/wiedehopf/tar1090-db) or
Wikipedia (https://en.wikipedia.org/wiki/List_of_airline_codes) was used.
When comparing which version of the Directive was used, check the generation timestamp in this file
with the release schedule in Section 1-1-6
(https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap1_section_1.html).
If you plan to use this module in other projects, please reference the original project:
https://github.com/WeegeeNumbuh1/FlightGazer \"\"\"\n\n"""
user = UserAgent(browsers=['Chrome', 'Edge', 'Firefox'], platforms='desktop')
HTML_header = {'User-Agent': str(user.random)}
tar1090db_verstr = 'None'

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

def strip_accents(s: str, skip_fallback: bool = False) -> str:
    """ Taken directly from FlightGazer.
    Falls back to substituting an underscore if the resultant string isn't fully ASCII,
    unless `skip_fallback` is True. This can also de-Zalgo text as a neat side-effect.
    ### Examples:
    >>> Manhattan Café -> Manhattan Cafe
    >>> Matikanetannhäuser -> ̶M̶a̶m̶b̶o̶  Matikanetannhauser
    >>> bröther may i have some ōâtš -> brother may i have some oats
    >>> “Peau Vavaʻu” -> _Peau Vava_u_

    ### References
    https://stackoverflow.com/a/518232 """
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                    if unicodedata.category(c) != 'Mn')
    if skip_fallback:
        return s
    if s.isascii():
        return s
    else:
        return ''.join([s_ if s_.isascii() else "_" for s_ in s])

def normalize(s: str) -> str:
    """ Removes excess whitespace and ensures everything is a single line """
    try:
        return " ".join(s.split()).strip()
    except Exception:
        return s

def extractor() -> dict | None:
    """ Download the compressed operators database from tar1090-db and return
    a dictionary of it for use later. Returns None for any failure. """
    """ Programmer's notes: the file is a javascript 'database' that's conveniently
    in the form of {'ABC': {'n': name, 'c': country, 'r': callsign/telephony}, ...} """
    global tar1090db_verstr
    print("Downloading operators database from tar1090-db...")
    try:
        download_start = perf_counter()
        dataset3 = requests.get(tar1090db, headers=HTML_header, timeout=5)
        download_end = (perf_counter() - download_start)
        dataset3.raise_for_status()
        if dataset3.status_code != 200:
            raise requests.HTTPError(f'Got status code {dataset3.status_code}') from None
        try:
            db_ver = requests.get(tar1090db_ver, headers=HTML_header, timeout=5)
            tar1090db_verstr = db_ver.text.strip()
        except Exception:
            pass
        download_size = len(dataset3.content)
        print(f"Successfully downloaded {(download_size / (1024 * 1024)):.2f} "
              f"MiB of data in {download_end:.2f} seconds.")
        print(f"Database version: {tar1090db_verstr}")
        print("Decompressing data...")
        decompressed = gzip.decompress(dataset3.content)
        return ast.literal_eval(decompressed.decode('utf-8'))
    except Exception as e:
        print(f"Failed to get database: {e}")
        return None

def wikipedia_fetcher() -> list:
    """ Grab data from Wikipedia for our operator friendly names.
    Returns a list of dictionaries, each with the keys
    {'IATA', 'ICAO', 'Airline', 'Call sign', 'Country/Region', 'Comments'}.
    If any error occurs, returns an empty list. """
    print("Downloading supplementary info from Wikipedia...")
    download_start = perf_counter()
    try:
        dataset2 = requests.get('https://en.wikipedia.org/wiki/List_of_airline_codes', headers=HTML_header, timeout=5)
        dataset2.raise_for_status()
        download_end = (perf_counter() - download_start)
        if dataset2.status_code != 200:
            raise requests.HTTPError(f'Got status code {dataset2.status_code}') from None
    except Exception as e:
        print(f"Failed get data from Wikipedia: {e}")
        return []

    download_size = len(dataset2.content)
    print(f"Successfully downloaded {(download_size / (1024 * 1024)):.2f} "
         f"MiB of data in {download_end:.2f} seconds.")
    find_start = perf_counter()
    print("Sorting data...")
    html2 = dataset2.text
    soup2 = bs(html2, 'html.parser')
    data_wikipedia = []
    print("Extracting data...")
    tables = soup2.find_all('table')
    entries_to_ignore_contains = [
        'efunct', # Defunct
        'ormerly', # Formerly
        'no longer allocated'
    ]
    blank = {
        'IATA': None,
        'ICAO': None,
        'Airline': None,
        'Call sign': None,
        'Country/Region': None,
        'Comments': None
    }
    print("Validating data...")
    try:
        for table in tables:
            headers = [th.get_text(strip=True, separator=" ") for th in table.find_all('th')]
            for row in table.find_all('tr'):
                cells = [td.get_text(strip=True, separator=" ") for td in row.find_all('td')]
                if cells:
                    data_wikipedia.append({k:v for k,v in zip(headers, cells)})
        for i, entry in enumerate(data_wikipedia):
            # for telephony comparison; ensure the string is in the same case
            comment = entry.get('Comments', '')
            if any(substring in comment for substring in entries_to_ignore_contains):
                data_wikipedia[i] = blank
                continue
            if entry.get('Call sign', ''):
                data_wikipedia[i]['Call sign'] = strip_accents(entry['Call sign'].strip().upper())

    except Exception as e:
        print(f"Failed to parse data from Wikipedia: {e}")
        return []

    print(f"Parsed {len(data_wikipedia)} rows from Wikipedia "
          f"in {(perf_counter() - find_start):.2f} seconds.")
    return data_wikipedia

def restore_old():
    if (backup := Path(f"{write_path}.old")).exists():
        write_path.unlink(missing_ok=True)
        backup.rename(write_path)

print("Downloading data from the FAA...")
try:
    download1 = perf_counter()
    dataset = requests.get(FAA_source, headers=HTML_header, timeout=5)
    dataset.raise_for_status()
except Exception as e:
    print(f"Failed to get data: {e}")
    print("Cannot continue, please try again at a later time.")
    sys.exit(1)

download_size = len(dataset.content)
print(f"Successfully downloaded {(download_size / (1024 * 1024)):.2f} "
        f"MiB of data in {(perf_counter() - download1):.2f} seconds.")
print("Parsing HTML...")
parse_start = perf_counter()
html = dataset.text
soup = bs(html, 'html.parser')
print(f"Data parsed in {(perf_counter() - parse_start):.2f} seconds.")
data = []
data2 = []
friendly_available = True
data_tar1090 = extractor()
if data_tar1090:
    print(f"tar1090-db returned {len(data_tar1090)} rows.")
else:
    print("Could not download operator database, falling back to using Wikipedia...")
    data2 = wikipedia_fetcher()
    if not data2:
        print("WARNING: friendly operator names will be unavailable in this dataset.")
        friendly_available = False

# make a backup
print(f"Backing up current database as '{write_path}.old'...")
write_path.rename(f"{write_path}.old")

print(f"Writing to {write_path}...")

write_start = perf_counter()
date_gen_str = datenow.strftime("%Y-%m-%dT%H:%M:%SZ")
with open(write_path, 'w', encoding='utf-8') as file:
    file.write(header_str)
    file.write(f"GENERATED = '{date_gen_str}'\n")
    file.write(f"# Used tar1090-db version: {tar1090db_verstr}\n\n")
    if not friendly_available:
        file.write("# NOTICE: There are no \'friendly\' names in this dataset.\n\n")
    for i, table in enumerate(soup.find_all('table')):
        rows = table.find_all('tr')
        file.write(f"{alphabet[i]}_TABLE = [\n")
        letter_section = []
        for j, row in enumerate(rows):
            cols = row.find_all('td')
            if len(cols) > 0:
                ICAO_name = cols[0].text.strip().upper()
                friendly = ''
                if data_tar1090:
                    entry: dict = data_tar1090.get(ICAO_name, {})
                    friendly = strip_accents(entry.get('n', ''))
                elif data2:
                    if (matching_entry := dict_lookup(data2, 'ICAO', ICAO_name)) is not None:
                        if (matching_callsign := dict_lookup(data2, 'Call sign', cols[3].text.strip().upper())) is not None:
                            # callsign from the FAA and Wikipedia matches, use this name
                            friendly = strip_accents(matching_callsign.get('Airline', ''))
                        else:
                            # just use the airline name
                            friendly = strip_accents(matching_entry.get('Airline', ''))
                        # if the country does match (name got reallocated somewhere else) just fall back on the FAA name
                        if cols[2].text.strip() != matching_entry.get('Country/Region', '').upper():
                            friendly = ''

                letter_section.append({
                    '3Ltr': normalize(cols[0].text),
                    'Company': normalize(cols[1].text),
                    'Country': normalize(cols[2].text),
                    'Telephony': normalize(cols[3].text),
                    'FriendlyName': normalize(friendly),
                })
                file.write(f"    {letter_section[-1]},\n")
        file.write(f"] # {j} entries.\n\n")
        data.extend(letter_section)
        print(f"Wrote table '{alphabet[i]}' with {j} entries.")
    file.write(f"# {len(data)} entries in total.\n")

print(f"A total of {len(data)} entries were written in "
      f"{(perf_counter() - write_start):.2f} seconds.")
print(f"Resulting file size: {(write_path.stat().st_size) / (1024):.3f} KiB.")
print(f"\nChecking the new file's validity...")
valid_check = True
try:
    importlib.reload(op)
    new_version = op.GENERATED
    print(f"New file generated on: {new_version}")
    from random import choices
    if new_version != old_version:
        # test that we can extract a result
        result_test = []
        random_icaos = set()
        # generate a minimum of 100 random, but valid callsigns
        for _ in range(500): # bail out if we can't hit the minimum
            test_icao = ''.join(choices(alphabet, k=3))
            if test_icao in random_icaos:
                continue
            random_icaos.add(test_icao)
            if (lookup := dict_lookup(getattr(op, f'{test_icao[0]}_TABLE'), '3Ltr', test_icao)) is not None:
                result_test.append(lookup)
            if len(result_test) >= 100:
                break

        for entry in result_test:
            if not (_ := entry['Company']): # every entry needs a name at minimum
                raise AttributeError('Unable to fetch required name from database.')
            _ = entry['FriendlyName']

        print("Updated database successfully passed validity checks.")
except Exception as e:
    print(f"ERROR: New database failed check:\n{e}")
    print("Restoring older version...")
    restore_old()
    valid_check = False

print(f"Total wall time: {perf_counter() - script_start:.2f} seconds.")
print("\n***** Done. *****")
if valid_check:
    sys.exit(0)
else:
    sys.exit(1)