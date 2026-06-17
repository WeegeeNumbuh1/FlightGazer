""" This script imports the `aircraft.csv.gz` file that's kept up-to-date from wiedehopf's `tar1090-db` repository
(https://github.com/wiedehopf/tar1090-db/tree/csv) and converts it into a sqlite3 database.
Additional credit goes to Mictronics (https://www.mictronics.de/aircraft-database/index.php)
and all the volunteers for maintaining the actual database.
This script was created for use with the FlightGazer project (https://github.com/WeegeeNumbuh1/FlightGazer).
This database is covered by the ODC-By License (https://opendatacommons.org/licenses/by/1-0/). """
# by WeegeeNumbuh1
# Last updated: v.11.3.0

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
import re
import socket
import os
from shutil import chown
from argparse import ArgumentParser
script_start = perf_counter()
CURRENT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = Path(f"{CURRENT_DIR}/database.db")
if os.name == 'posix':
    try:
        DB_OWNER = OUTPUT_FILE.owner()
    except Exception:
        DB_OWNER = None
URL = 'https://raw.githubusercontent.com/wiedehopf/tar1090-db/csv/aircraft.csv.gz'
TYPES_URL = "https://github.com/wiedehopf/tar1090-db/raw/refs/heads/master/db/icao_aircraft_types2.js"
leading_icao_chars = '0123456789ABCDEF'

# service specific stuff
SYSTEMD_NOTIFY_SOCKET = os.environ.get('NOTIFY_SOCKET')
INIT_PROGRESS_FILE = Path('/run/FlightGazer/init_progress') # for the splash screen
# note for the splash screen values: 55-94% as this is run in the 3rd stage of initialization
init_progress_percentage = 55

if __name__ != '__main__':
    print("This script cannot be imported as a module.")
    print("Run this directly from the command line.")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("This script requires the 'requests' module.")
    print("You can install it using 'pip install requests'.")
    sys.exit(1)

args_main = ArgumentParser()
args_main.add_argument('-r', '--rebuild',
                action='store_true',
                help=("Rebuild the database. "
                      "Useful to ensure entries are sorted by their hex. "
                      "Takes longer on slow systems.")
                )
args_init = args_main.parse_args()
if args_init.rebuild:
    REBUILD: bool = True
else:
    REBUILD = False

def update_init_progress() -> None:
    """ Update the progress file, if it exists.
    Reads the global `init_progress_percentage` """
    if INIT_PROGRESS_FILE.is_file():
        try:
            with open(INIT_PROGRESS_FILE, 'w') as fi:
                fi.write(f'{int(round(init_progress_percentage))}')
        except Exception:
            pass

def systemd_notify(message: str) -> None:
    """ Pulled from FlightGazer """
    notify_socket = SYSTEMD_NOTIFY_SOCKET
    if not notify_socket:
        return

    if notify_socket.startswith('@'):
        notify_socket = '\0' + notify_socket[1:]

    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC) as sock:
        sock.sendto(message.encode(), notify_socket)

current_db_ver = None
if (jrnl := Path(f"{CURRENT_DIR}/database.db-journal")).exists():
    print("Warning: It appears this script was terminated before it could write\n"
    "out the database. To maintain a consistent state, the database will be fully rebuilt.\n")
    jrnl.unlink(missing_ok=True)
    OUTPUT_FILE.unlink(missing_ok=True)

db_size_old = 0
if OUTPUT_FILE.exists():
    db_size_old = OUTPUT_FILE.stat().st_size
    _result = None
    _connection = sqlite3.connect(f"file:{OUTPUT_FILE.as_posix()}?mode=rw", uri=True)
    _connection.row_factory = sqlite3.Row
    _cursor = _connection.execute("SELECT * FROM DB_INFO ORDER BY ROWID ASC LIMIT 1")
    _result = _cursor.fetchone()
    _cursor = _connection.execute("PRAGMA journal_mode;")
    journal_mode = dict(_cursor.fetchone()).get('journal_mode', 'Unknown')
    # convert older databases to write ahead logging
    if journal_mode != 'wal':
        _connection.execute("PRAGMA journal_mode=WAL;")
        _connection.commit()
    else:
        # clean-up the -shm and -wal files if a previous update did not fully commit
        _connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    _cursor.close()
    _connection.close()
    if _result is not None:
        current_db_ver = dict(_result).get('version', 'unknown')
        if os.name == 'posix' and DB_OWNER:
            chown(OUTPUT_FILE, user=DB_OWNER)
    else:
        current_db_ver = "unknown"
    print(f"Database already exists, current version: {current_db_ver}")
else:
    print("Database is not present.")
    journal_mode = None
init_progress_percentage += 3 # 58
update_init_progress()

try:
    get_db_ver = requests.get("https://raw.githubusercontent.com/wiedehopf/tar1090-db/refs/heads/csv/version", timeout=5)
    get_db_ver.raise_for_status()
    if get_db_ver.status_code == 200:
        db_ver = get_db_ver.text.strip()
    else:
        db_ver = "unknown"
        raise requests.HTTPError(f"Got status code {get_db_ver.status_code}") from None
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
        sys.exit(1)
except requests.RequestException as e:
    print(f"Failed to download the CSV file: {e}")
    sys.exit(1)
download_size = len(response.content)
print(f"Successfully downloaded {(download_size / (1024 * 1024)):.2f} "
      f"MiB of data in {download_end:.2f} seconds.")
if current_db_ver is None:
    print(f"Downloaded database version: {db_ver}")

print("Fetching aircraft types data...")
types_data_available = False
try:
    types_download_start = perf_counter()
    types_response = requests.get(TYPES_URL, timeout=10)
    types_response.raise_for_status()
    if types_response.status_code != 200:
        print(f"Failed to download the aircraft types data. Status code: {types_response.status_code}")
        raise requests.HTTPError
    print("Successfully downloaded aircraft types in "
          f"{perf_counter() - types_download_start:.2f} seconds.")
    types_data_available = True
except requests.RequestException as e:
    print(f"Failed to download the aircraft types data: {e}")
    print("Continuing without aircraft types data.\n"
          "This may affect the accuracy of aircraft type descriptions for some ICAO addresses.")

init_progress_percentage += 4 # 62
update_init_progress()
""" Programmer's notes: The way the original version of this script handled the database was to:
decompress the gzip, load the CSV into a list, load the types data and convert it into a dict,
fill-in the missing data in the CSV with the types, then write it all to the database, all in memory.
This was faster and simpler, however it was very punishing for low memory systems like a
Raspberry Pi Zero where peak memory usage running this script was about 300+ MiB
(out of the roughly 400 available). Now, we stream directly from the gzip which
dramatically lowers memory usage to 40 MiB in exchange for this being much more CPU-bound. """

def count_csv_rows(content):
    """ Count total rows in CSV without storing them """
    row_count = 0
    for _ in stream_csv_from_gzip(content):
        row_count += 1
    return row_count

def stream_csv_from_gzip(content):
    """ Stream CSV rows directly from gzipped content """
    compressed = BytesIO(content)
    with gzip.GzipFile(fileobj=compressed, mode='rb') as f:
        reader = csv.DictReader(
            (line.decode('utf-8') for line in f),
            fieldnames=['icao', 'reg', 'type', 'flags', 'desc', 'year', 'ownop', 'blank'],
            delimiter=';'
        )
        for row in reader:
            yield row

print("Enumerating the data...")
csv_processing_start = perf_counter()
try:
    total_rows = count_csv_rows(response.content)
except Exception as e:
    print(f"ERROR: Failed to parse database! - {e}")
    sys.exit(1)
csv_time = perf_counter() - csv_processing_start
print(f"Processing took {csv_time:.2f} seconds "
      f"({int(total_rows / csv_time)} "
      "rows/sec).")
print(f"Total rows to process: {total_rows}")
if total_rows == 0:
    print("ERROR: 0 rows returned - There is no data to parse!")
    sys.exit(1)
init_progress_percentage += 8 # 70
update_init_progress()

def iter_types_from_js_bytes(content_bytes):
    """ Stream-parse a JS object like { 'TYPE': ['desc', ...], ... } from the gzipped bytes.
    Yields (type_key, value_list) lazily """
    compressed = BytesIO(content_bytes)
    with gzip.GzipFile(fileobj=compressed, mode='rb') as fh:
        # read line-by-line to avoid loading whole file
        pattern = re.compile(r"""['"]([^'"]+?)['"]\s*:\s*(\[[^\]]*\])""")
        for raw_line in fh:
            try:
                line = raw_line.decode('utf-8', errors='ignore')
            except Exception:
                continue
            # remove obvious escape-backslashes that would break literal_eval
            line = line.replace("\\/", "/").replace("\\\"", "\"")
            for m in pattern.finditer(line):
                key = m.group(1)
                val_str = m.group(2)
                try:
                    val = ast.literal_eval(val_str)
                except Exception:
                    # skip invalid bits
                    continue
                yield key, val

def process_types_data(types_response) -> dict:
    """ Process aircraft types data and return a mapping of types to descriptions """
    print("Formatting the types data...")
    types_format_start = perf_counter()

    types_map = {}

    # def get_needed_types():
    #     """ Get set of aircraft types needing description """
    #     needed = set()
    #     for row in stream_csv_from_gzip(response.content):
    #         if row['type'] and not row['desc']:
    #             needed.add(row['type'])
    #             yield row['type']

    for key, val in iter_types_from_js_bytes(types_response.content):
        types_map[key] = val[0] if val else ''

    # # build types mapping only for needed types
    # # re-enable this if at some point the types list gets as large as the database
    # needed_types = set(get_needed_types())
    # if needed_types:
    #     for key, val in iter_types_from_js_bytes(types_response.content):
    #         if key in needed_types:
    #             types_map[key] = val[0] if val else ''
    #             needed_types.remove(key)
    #             if not needed_types:
    #                 break

    print(f"Formatting took {perf_counter() - types_format_start:.2f} seconds, "
          f"with {len(types_map)} types available.")
    return types_map

def process_aircraft_data(response_content, types_map=None, batch_size=10000):
    """ Stream & process aircraft data and yield batches to insert into the database. """
    print("Committing to database...")
    global init_progress_percentage

    batches = {char: [] for char in leading_icao_chars}
    batch = []
    processed_count = 0
    empty_desc = 0
    entry_updates = 0
    last_percentage = 0

    for row in stream_csv_from_gzip(response_content):
        processed_count += 1
        current_percentage = (processed_count / total_rows) * 100

        # update description if types data is available
        if types_map and row['type'] and not row['desc']:
            empty_desc += 1
            new_desc = types_map.get(row['type'], '')
            row['desc'] = new_desc
            if new_desc:
                entry_updates += 1

        icao = row['icao']
        if not icao:
            continue
        leading_char = icao[0]
        if leading_char not in leading_icao_chars:
            continue

        batches[leading_char].append((
            row['icao'], row['reg'], row['type'], row['flags'],
            row['desc'], row['year'], row['ownop']
        ))

        if len(batches[leading_char]) >= batch_size:
            yield batches[leading_char], leading_char
            batches[leading_char] = []

        if current_percentage >= last_percentage + 10:
            print(f"{int(current_percentage)}% complete ({processed_count}/{total_rows})")
            last_percentage = (current_percentage // 10) * 10
            init_progress_percentage += 2.4
            update_init_progress()

    # yield remaining batch
    for leading_char, batch in batches.items():
        if batch:
            yield batch, leading_char

    if types_map:
        print(f"Filled {entry_updates} out of {empty_desc} "
              f"({(entry_updates / empty_desc) * 100:.1f}%) empty aircraft descriptions.")

date_now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
try:
    username = getuser()
except OSError:
    username = "< Unknown >"
machine = uname()
machine_name = (f"\'{machine.node}\', running {machine.system} "
                f"{machine.release} [ {machine.version} on {machine.machine} ]")
license_string = "Open Data Commons Attribution License"

# now we do the actual database stuff
with sqlite3.connect(OUTPUT_FILE) as conn:
    conn.execute("PRAGMA journal_mode=WAL;")
    cursor = conn.cursor()

    print("Initializing tables...")
    table_start = perf_counter()
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
        if REBUILD:
            print("Rebuilding.")
            cursor.execute(f"DELETE FROM ICAO_{char}")
            print(f"Table initialization took {perf_counter() - table_start:.2f} seconds.")

    # process types data if available
    types_map = None
    if types_data_available:
        try:
            types_map = process_types_data(types_response)
        except Exception as e:
            print(f"Failed to parse types data - {e}")
            print("Continuing without aircraft types data.\n"
                  "This may affect the accuracy of aircraft type descriptions for some ICAO addresses.")
            types_data_available = False
            types_map = None

    print(f"Writing to \'{OUTPUT_FILE}\'.")
    print("Estimated time: "
          f"{round(csv_time * 2.6, 1)}-"
          f"{round(csv_time * 5.5, 1)} seconds.") # from testing
    # extend the timeout based on how fast we're running through this
    systemd_notify(f"EXTEND_TIMEOUT_USEC={int(round(csv_time * 8_000_000, 0))}")
    write_start = perf_counter() # actually start the timing from here
    # process aircraft data straight from the gzipped files (this is CPU-bound)
    for batch, leading_char in process_aircraft_data(response.content, types_map):
        cursor.executemany(f"""
            INSERT INTO ICAO_{leading_char}
            (icao, reg, type, flags, desc, year, ownop)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(icao) DO UPDATE SET
                reg = excluded.reg,
                type = excluded.type,
                flags = excluded.flags,
                desc = excluded.desc,
                year = excluded.year,
                ownop = excluded.ownop
            WHERE
                reg != excluded.reg OR
                type != excluded.type OR
                flags != excluded.flags OR
                desc != excluded.desc OR
                year != excluded.year OR
                ownop != excluded.ownop;
        """, batch)
        conn.commit()

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

    cursor.execute("DELETE FROM DB_INFO")
    cursor.execute("""
        INSERT INTO DB_INFO (version, created_date, created_by, machine, license)
        VALUES (?, ?, ?, ?, ?)
        """, (db_ver, date_now, username, machine_name, license_string))

    conn.commit()

    if journal_mode == 'wal':
        print("Cleaning up...")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    total_changes = conn.total_changes

conn.close()

if os.name == 'posix' and DB_OWNER:
    chown(OUTPUT_FILE, user=DB_OWNER)

db_size_new = OUTPUT_FILE.stat().st_size
print(f"Modifications took {perf_counter() - write_start:.2f} seconds.")
print(f"Database size: {db_size_new / (1024 * 1024):.3f} MiB ")
print(f"Deltas: {(db_size_new - db_size_old) / 1024:.2f} KiB, {total_changes} changes.")
print("\n***** Done. *****")
print(f"Total wall time: {perf_counter() - script_start:.2f} seconds.")
print("Database importer exiting...")
sys.exit(0)