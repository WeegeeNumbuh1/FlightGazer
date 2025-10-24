""" This script imports the `aircraft.csv.gz` file that's kept up-to-date from wiedehopf's `tar1090-db` repository
(https://github.com/wiedehopf/tar1090-db/tree/csv) and converts it into a sqlite3 database.
Additional credit goes to Mictronics (https://www.mictronics.de/aircraft-database/index.php) for maintaining the actual database.
This script was created for use with the FlightGazer project (https://github.com/WeegeeNumbuh1/FlightGazer)
and is intended to be used in conjunction with FlightGazer's `FlightGazer-init.sh` script.
This database is covered by the ODC-By License (https://opendatacommons.org/licenses/by/1-0/). """
# by WeegeeNumbuh1
# Last updated: October 2025

print("********** FlightGazer Aircraft Database Importer **********\n")
import csv
from pathlib import Path
import sqlite3
import gzip
import sys
from io import BytesIO
import ast
from time import perf_counter
from datetime import datetime, timezone
from getpass import getuser
from platform import uname
import gc
import threading
from time import sleep
CURRENT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = Path(f"{CURRENT_DIR}/database.db")
URL = 'https://raw.githubusercontent.com/wiedehopf/tar1090-db/csv/aircraft.csv.gz'
TYPES_URL = "https://github.com/wiedehopf/tar1090-db/raw/refs/heads/master/db/icao_aircraft_types2.js"
leading_icao_chars = '0123456789ABCDEF'

if __name__ != '__main__':
    print("This script cannot be imported as a module.")
    print("Run this directly from the command line.")
    raise sys.exit(1)

try:
    import requests
except (ImportError, ModuleNotFoundError):
    print("This script requires the 'requests' module.")
    print("You can install it using 'pip install requests'.")
    raise sys.exit(1)

try:
    from psutil import virtual_memory
except (ImportError, ModuleNotFoundError):
    pass

def still_alive():
    """ If it takes awhile to generate the database, print out
    a reassurance message that this script is still working every 30 seconds. """
    indicator = 0
    while True:
        sleep(30)
        indicator += 30
        print(f"--- Script is still working. ({indicator} seconds have passed) ---", flush=True)

current_db_ver = None
threading.Thread(target=still_alive, daemon=True).start()
if (jrnl := Path(f"{CURRENT_DIR}/database.db-journal")).exists():
    print("Warning: It appears this script was terminated before it could write\n"
    "out the database. To maintain a consistent state, the database will be fully rebuilt.\n")
    jrnl.unlink(missing_ok=True)
    OUTPUT_FILE.unlink(missing_ok=True)

if OUTPUT_FILE.exists():
    _connection = sqlite3.connect(f"file:{OUTPUT_FILE.as_posix()}?mode=ro", uri=True)
    _connection.row_factory = sqlite3.Row
    _cursor = _connection.execute("SELECT * FROM DB_INFO ORDER BY ROWID ASC LIMIT 1")
    _result = _cursor.fetchone()
    _cursor.close()
    _connection.close()
    if _result is not None:
        current_db_ver = dict(_result).get('version', 'unknown')
    else:
        current_db_ver = "unknown"
    print(f"Database already exists, current version: {current_db_ver}")

try:
    get_db_ver = requests.get("https://raw.githubusercontent.com/wiedehopf/tar1090-db/refs/heads/csv/version", timeout=5)
    get_db_ver.raise_for_status()
    if get_db_ver.status_code == 200:
        db_ver = get_db_ver.text.strip()
    else:
        db_ver = "unknown"
        raise requests.HTTPError(f"Got status code {get_db_ver.status_code}")
except requests.RequestException as e:
    print(f"Failed to fetch the database version from online: {e}")
    print(f"Unable to continue.")
    sys.exit(1)

if current_db_ver is not None:
    print(f"Database version available online:        {db_ver}")
    if current_db_ver == db_ver:
        print("Database versions are the same, no need to update.")
        print("\n***** Done. *****")
        sys.exit(0)
    else:
        print("Database online is different than the one present; will update to latest data.")

print("Downloading aircraft data from the tar1090-db repository...")
download_start = perf_counter()
try:
    response = requests.get(URL, timeout=10)
    download_end = (perf_counter() - download_start)
    response.raise_for_status()
    if response.status_code != 200:
        print(f"Failed to download the CSV file. Status code: {response.status_code}")
        raise sys.exit(1)
except requests.RequestException as e:
    print(f"Failed to download the CSV file: {e}")
    raise sys.exit(1)
download_size = len(response.content)
print(f"Successfully downloaded {(download_size / (1024 * 1024)):.2f} MiB of data in {download_end:.2f} seconds.")

LOW_MEM = False
try:
    mem = virtual_memory()
    if (mem.total / (1024 ** 2)) < 512:
        LOW_MEM = True
    # Note: we don't care if there's overhead when calling the garbage collector,
    # the more important thing is to not have this script lock up the system when running
    # these operations that need to allocate a (relatively) sizable chunk of memory.
    # From the author's experience, running this script would inevitably freeze a Raspberry Pi Zero
    # system before implementing this check if it's already running a lot of stuff in memory.
    # It's assumed that if the system memory is already this small, we're dealing with
    # a potato and it'll take more than a minute for this script to complete anyway.
    # As reference, a modern AMD Zen 5 system completes this script in about 5 seconds.
except:
    pass

print("Decompressing...")
decompress_start = perf_counter()
compressed_data = BytesIO(response.content)
del response
if LOW_MEM: gc.collect()
with gzip.GzipFile(fileobj=compressed_data, mode='rb') as f:
    csv_data = f.read().decode('utf-8')
del compressed_data
if LOW_MEM: gc.collect()
decompress_end = (perf_counter() - decompress_start)
csv_size = len(csv_data)
print(f"Decompressed {(csv_size / (1024 * 1024)):.3f} MiB in {decompress_end:.2f} seconds. "
      f"({(download_size / csv_size)*100:.1f}% ratio)")

if LOW_MEM:
    print("\n*** Warning: This is a low memory system! "
          f"({(mem.total / (1024 ** 2)):.1f} MiB) ***")
    print("Your device may struggle to complete the next tasks.")
    print("If the device locks up, use this script to generate\n"
          "the database on another computer, and then transfer the\n"
          f"database to \'{CURRENT_DIR}\'\n")

print("Loading CSV file...")
# Read in the csv file (no header row)
# fieldnames: ['icao', 'reg', 'type', 'flags', 'desc', 'year', 'ownop', 'blank']
# The last field is a blank field that should be ignored (it was designed for readsb)
read_start = perf_counter()
parsed = []
reader = csv.DictReader(
    csv_data.splitlines(),
    fieldnames=['icao', 'reg', 'type', 'flags', 'desc', 'year', 'ownop', 'blank'],
    delimiter=';'
    )
del csv_data
if LOW_MEM: gc.collect()
try:
    for row in reader:
        parsed.append(row)
    print(f"CSV file loaded in {perf_counter() - read_start:.2f} seconds with {len(parsed)} rows.")
    del reader, row
    if LOW_MEM: gc.collect()
except csv.Error as e:
    print(f"Failed to parse the CSV file ({e}).")
    print(f"Unable to continue.")
    sys.exit(1)

print("Fetching aircraft types data...")
types_data_available = False
try:
    types_response = requests.get(TYPES_URL, timeout=10)
    types_response.raise_for_status()
    if types_response.status_code != 200:
        print(f"Failed to download the aircraft types data. Status code: {types_response.status_code}")
        raise requests.HTTPError
    print(f"Successfully downloaded aircraft types.")
    types_data_available = True
except requests.RequestException as e:
    print(f"Failed to download the aircraft types data: {e}")
    print("Continuing without aircraft types data.\n"
          "This may affect the accuracy of aircraft type descriptions for some ICAO addresses.")
if types_data_available:
    compressed_data = BytesIO(types_response.content)
    with gzip.GzipFile(fileobj=compressed_data, mode='rb') as f:
        js_data = f.read().decode('utf-8')
    js_data_cleaned = js_data.replace("\\", "") # remove escaped slashes
    del compressed_data, types_response, js_data
    if LOW_MEM: gc.collect()
    # lucky us, the data is a valid python dict
    newTypes = ast.literal_eval(js_data_cleaned)
    del js_data_cleaned
    if LOW_MEM: gc.collect()
    print("Filling missing aircraft descriptions in database...")
    fill_start = perf_counter()
    empty_desc = 0
    entry_updates = 0
    for index, row in enumerate(parsed):
        if row['type'] and not row['desc']:
            empty_desc += 1
            parsed[index]['desc'] = newTypes.get(row['type'], [''])[0]
            if parsed[index]['desc']:
                entry_updates += 1
    print(f"Filled {entry_updates} out of {empty_desc} "
          f"({(entry_updates / empty_desc) * 100:.1f}%) empty aircraft descriptions "
          f"in {perf_counter() - fill_start:.2f} seconds.")
    del newTypes
    if LOW_MEM: gc.collect()

print(f"Writing to \'{OUTPUT_FILE}\'...")
date_now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
try:
    username = getuser()
except OSError:
    username = "< Unknown >"
machine = uname()
machine_name = f"\'{machine.node}\', running {machine.system} {machine.release} [ {machine.version} on {machine.machine} ]"
license_string = "Open Data Commons Attribution License"

write_start = perf_counter()
rows_in_db = len(parsed)
# Write to a sqlite database
# Each table will be named after the first character of the ICAO code
with sqlite3.connect(OUTPUT_FILE) as conn:
    cursor = conn.cursor()
    # Create a table for each leading character
    for char in leading_icao_chars:
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS ICAO_{char} (
                icao TEXT PRIMARY KEY,
                reg TEXT,
                type TEXT,
                flags INTEGER,
                desc TEXT,
                year INTEGER,
                ownop TEXT
            );
        """)
        cursor.execute(f"DELETE FROM ICAO_{char}")

    # check if we're using an older database that doesn't have this column
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='DB_INFO';")
    info_table_exists = cursor.fetchone()
    if info_table_exists:
        cursor.execute(f"PRAGMA table_info(DB_INFO);")
        db_info_cols = [col[1] for col in cursor.fetchall()]
        if 'license' not in db_info_cols:
            cursor.execute("DROP TABLE IF EXISTS DB_INFO;")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS DB_INFO (
            version TEXT PRIMARY KEY,
            created_date TEXT,
            created_by TEXT,
            machine TEXT,
            license TEXT
        );
    """)

    # Insert the data into the respective tables
    last_percentage = 0
    for i, row in enumerate(parsed):
        current_percentage = ((i + 1) / rows_in_db) * 100
        icao = row['icao']
        if icao[0] in leading_icao_chars:
            cursor.execute(f"""
                INSERT OR REPLACE INTO ICAO_{icao[0]} (icao, reg, type, flags, desc, year, ownop)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (row['icao'], row['reg'], row['type'], row['flags'], row['desc'], row['year'], row['ownop']))
        if current_percentage >= last_percentage + 10:
            print(f"{last_percentage + 10}% complete ({i + 1}/{rows_in_db})")
            last_percentage += 10

    cursor.execute("DELETE FROM DB_INFO")
    cursor.execute("""
        INSERT INTO DB_INFO (version, created_date, created_by, machine, license)
        VALUES (?, ?, ?, ?, ?)
        """, (db_ver, date_now, username, machine_name, license_string))

    conn.commit()
conn.close()

print(f"{(OUTPUT_FILE.stat().st_size) / (1024 * 1024):.3f} MiB of records "
      f"written to database in {perf_counter() - write_start:.2f} seconds.")
print("\n***** Done. *****")
sys.exit(0)