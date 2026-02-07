""" Script that downloads the FAA's list of ICAO airline codes and formats it
into a series of lookup tables separated by letter for use with FlightGazer or any other python program.
Can be used to update the database in the future.
To see changes on the FAA's side: https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap0_cam.html """
# by WeegeeNumbuh1
# Last updated: January 2026
# Released in conjunction with Flightgazer version: v.9.9.3

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

print("Continuing update.")
# load in all the other modules
import unicodedata
import importlib
import csv
from io import StringIO
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
fg_db = 'https://github.com/WeegeeNumbuh1/FlightGazer-airlines-db/raw/refs/heads/master/operators.csv'
fg_db_ver = 'https://github.com/WeegeeNumbuh1/FlightGazer-airlines-db/raw/refs/heads/master/version'
header_str = """\"\"\" Importable python module for aviation callsign lookup.
All data sourced from the Federal Aviation Administration, Directive No. JO 7340.2N, Chapter 3, Section 3.
For the operators' friendly names, the FlightGazer-airlines-db was used.
When comparing which version of the Directive was used, check the generation timestamp in this file
with the release schedule in Section 1-1-6
(https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap1_section_1.html).
If you plan to use this module in other projects, please reference the original project:
https://github.com/WeegeeNumbuh1/FlightGazer \"\"\"\n\n"""
user = UserAgent(browsers=['Chrome', 'Edge', 'Firefox'], platforms='desktop')
HTML_header = {'User-Agent': str(user.random)}
fg_db_verstr = 'Unknown'

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

def fg_db_fetcher() -> dict:
    """ Grab and parse the FlightGazer aircraft database.
    Returns a dictionary in a form similar to the tar1090-db """
    """ Header: '3Ltr','Company','Country','Telephony','FriendlyName' """
    global fg_db_verstr
    download_start = perf_counter()
    print("Pulling additional data from the FlightGazer-aircraft-db database...")
    try:
        dataset2 = requests.get(fg_db, headers=HTML_header, timeout=5)
        dataset2.raise_for_status()
        download_end = (perf_counter() - download_start)
        if dataset2.status_code != 200:
            raise requests.HTTPError(f'Got status code {dataset2.status_code}') from None
    except Exception as e:
        print(f"Failed get data: {e}")
        return {}
    download_size = len(dataset2.content)
    print(f"Successfully downloaded {(download_size / (1024 * 1024)):.2f} "
         f"MiB of data in {download_end:.2f} seconds.")
    try:
        db_ver = requests.get(fg_db_ver, headers=HTML_header, timeout=5)
        fg_db_verstr = db_ver.text.strip()
        print(f"Using database version: {fg_db_verstr}")
    except Exception:
        pass
    csv_start = perf_counter()
    csv_reader = csv.DictReader(StringIO(dataset2.text))
    try:
        data = {row['3Ltr']: row for row in csv_reader}
    except KeyError:
        print(f"Failed to parse CSV: {e}")
        return {}
    print(f"Processed {len(data)} entries in {(perf_counter() - csv_start) * 1000:.3} ms.")
    return data

def restore_old():
    print("Restoring older version...")
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
data_fg_db = fg_db_fetcher()
if not data_fg_db:
    print("Failed to fetch data from the FlightGazer-airlines-db database.")
    print("Cannot continue, please try again at a later time.")
    sys.exit(1)

# make a backup
if write_path.exists():
    print(f"Backing up current database as '{write_path}.old'...")
    write_path.rename(f"{write_path}.old")

print(f"Writing to {write_path}...")

write_start = perf_counter()
date_gen_str = datenow.strftime("%Y-%m-%dT%H:%M:%SZ")
icaos = set()
def write_new():
    with open(write_path, 'w', encoding='utf-8') as file:
        entrycount = 0
        file.write(header_str)
        file.write(f"GENERATED = '{date_gen_str}'\n")
        file.write(f"# Used FlightGazer-airlines-db: {fg_db_verstr}\n\n")
        for i, table in enumerate(soup.find_all('table')):
            rows = table.find_all('tr')
            file.write(f"{alphabet[i]}_TABLE = [\n")
            j = 0
            for row in rows:
                cols = row.find_all('td')
                if len(cols) > 0:
                    ICAO_name = strip_accents(cols[0].text.strip().upper())
                    if ICAO_name in icaos:
                        continue
                    icaos.add(ICAO_name)
                    friendly = ''
                    entry: dict = data_fg_db.get(ICAO_name, {})
                    friendly = strip_accents(entry.get('FriendlyName', ''))

                    section_row = {
                        '3Ltr': normalize(cols[0].text),
                        'Company': normalize(cols[1].text),
                        'Country': normalize(cols[2].text),
                        'Telephony': normalize(cols[3].text),
                        'FriendlyName': normalize(friendly),
                    }

                    file.write(f"    {section_row},\n")
                    j += 1

            file.write(f"] # {j} entries.\n\n")
            entrycount += j
            print(f"Wrote table '{alphabet[i]}' with {j} entries.")

        file.write(f"# {entrycount} entries in total.\n")

    print(f"A total of {entrycount} entries were written in "
        f"{(perf_counter() - write_start):.2f} seconds.")
    print(f"Resulting file size: {(write_path.stat().st_size) / (1024):.3f} KiB.")

try:
    write_new()
except Exception as e:
    print(f"Failed to generate new database:\n{e}")
    restore_old()
    sys.exit(1)

print(f"\nChecking the new file's validity...")
valid_check = True
try:
    if 'operators' in sys.modules:
        importlib.reload(op)
    else:
        sys.path.append(current_path)
        import operators as op
    new_version = op.GENERATED
    print(f"New file generated on: {new_version}")
    from random import choices
    if new_version != old_version:
        # test that we can extract a result
        result_test = []
        random_icaos = set()
        queries = 0
        min_success = 500
        db_speed_start = perf_counter()
        # generate a minimum of `min_success` random, but valid callsigns
        for _ in range(int(min_success * 5)): # bail out if we can't hit the minimum
            test_icao = ''.join(choices(alphabet, k=3))
            if test_icao in random_icaos:
                continue
            random_icaos.add(test_icao)
            queries += 1
            if lookup := dict_lookup(getattr(op, f'{test_icao[0]}_TABLE'), '3Ltr', test_icao):
                result_test.append(lookup)
            if len(result_test) >= min_success:
                print(f"Made {queries} queries to the new database. ("
                      f"{queries / (perf_counter() - db_speed_start):.0f} "
                      "queries/sec)"
                )
                break
        else:
            print(f"Made {queries} queries to the new database. ("
                f"{queries / (perf_counter() - db_speed_start):.0f} "
                "queries/sec)"
            )

        for entry in result_test:
            if not (_ := entry['Company']): # every entry needs a name at minimum
                raise AttributeError('Unable to fetch required name from database.')
            _ = entry['FriendlyName']

        print("Updated database successfully passed validity checks.")

except Exception as e:
    print(f"ERROR: New database failed check:\n{e}")
    restore_old()
    valid_check = False

print(f"Total wall time: {perf_counter() - script_start:.2f} seconds.")
print("\n***** Done. *****")
if valid_check:
    sys.exit(0)
else:
    sys.exit(1)