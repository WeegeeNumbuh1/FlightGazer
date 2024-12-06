#      _/_/_/_/ _/_/    _/            _/        _/       _/_/_/                                    
#     _/         _/         _/_/_/   _/_/_/  _/_/_/_/ _/         _/_/_/ _/_/_/_/   _/_/   _/  _/_/
#    _/_/_/     _/    _/   _/    _/ _/    _/  _/     _/  _/_/ _/    _/     _/   _/_/_/_/ _/_/     
#   _/         _/    _/   _/    _/ _/    _/  _/     _/    _/ _/    _/   _/     _/       _/        
#  _/         _/_/    _/   _/_/_/ _/    _/    _/_/   _/_/_/   _/_/_/ _/_/_/_/   _/_/_/ _/          
#                             _/                               by: WeegeeNumbuh1      
#                        _/_/
                                     
""" 
A program heavily inspired by https://github.com/ColinWaddell/its-a-plane-python, but supplements flight information of
nearby planes with real-time ADS-B and UAT data from dump1090 and dump978. Uses the FlightAware API instead of FlightRadar24.
"""
    
# =============== Imports ==================
# ==========================================
import time
START_TIME: float = time.monotonic()
import datetime
STARTED_DATE: datetime = datetime.datetime.now()
VERSION: str = 'v.1.2.1 --- 2024-11-26'
import os
os.environ["PYTHONUNBUFFERED"] = "1"
import argparse
import sys
import math
from pathlib import Path
from contextlib import closing
from urllib.request import urlopen
import urllib.parse
import json
import signal
import threading
import asyncio
from collections import deque
from string import Formatter
import random
import getpass
# external imports
import requests
from pydispatch import dispatcher # pip install pydispatcher *not* pip install pydispatch
import schedule
import psutil
# utilities
import utilities.flags as flags
import utilities.registrations as registrations
from utilities.animator import Animator
from setup import frames

argflags = argparse.ArgumentParser(
    description="FlightGazer, a program to show dump1090 info to an RGB-Matrix display.",
    epilog="Protip: Ensure your location is set in your dump1090 configuration!"
    )
argflags.add_argument('-i', '--interactive',
                      action='store_true',
                      help="Print program output to console. If this flag is not used, this program runs silently."
                      )
argflags.add_argument('-e', '--emulate',
                      action='store_true',
                      help="Run the display in emulator mode via RGBMatrixEmulator."
                      )
argflags.add_argument('-d', '--nodisplay',
                      action='store_true',
                      help="Only show console output and do not use the display. Implies Interactive mode."
                      )
argflags.add_argument('-f', '--nofilter',
                      action='store_true',
                      help="Disable filtering and show all planes detected by dump1090.\n\
                      Disables API fetching and Display remains as a clock.\n\
                      Implies Interactive mode."
                      )
args = argflags.parse_args()
if args.interactive:
    INTERACTIVE: bool = True
else:
    INTERACTIVE = False
if args.emulate:
    EMULATE: bool = True
else:
    EMULATE = False
if args.nodisplay:
    NODISPLAY: bool = True
    INTERACTIVE = True
else:
    NODISPLAY = False
if args.nofilter:
    NOFILTER: bool = True
    INTERACTIVE = True
else:
    NOFILTER = False

FORGOT_TO_SET_INTERACTIVE: bool = False

# =========== Initialization I =============
# ==========================================

if __name__ != '__main__':
    print("FlightGazer cannot be imported as a module.")
    sys.exit(1)

CURRENT_DIR = Path(__file__).resolve().parent
print(f"FlightGazer Version: {VERSION}")
print(f"Script started: {STARTED_DATE.replace(microsecond=0)}")
print(f"We are running in \'{CURRENT_DIR}\'\nUsing: \'{sys.executable}\' as \'{getpass.getuser()}\'")
FLYBY_STATS_FILE = Path(f"{CURRENT_DIR}/flybys.csv")
API_URL: str = "https://aeroapi.flightaware.com/aeroapi/"
DUMP1090_IS_AVAILABLE: bool = False
""" If we fail to load dump1090, set to False and continue. We assume it isn't loaded at first. """
LOOP_INTERVAL: float = 2
""" in seconds. Affects how often we poll `dump1090`'s json (which itself atomically updates every second).
Affects how often other processing threads handle data as they are triggered on every update.
Should be left at 2 (or slower) """

# load in all the display-related modules
DISPLAY_VALID: bool = True
if NODISPLAY == False:
    try:
        try:
            if EMULATE == True: raise Exception
            from rgbmatrix import graphics
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
        except:
            # this is for debugging display output outside of physical hardware
            from RGBMatrixEmulator import graphics
            from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
        
        # these modules depend on the above, so they should load successfully at this point,
        # but if they break somehow, we can still catch it
        from setup import colors, fonts

        if 'RGBMatrixEmulator' in sys.modules:
            # INTERACTIVE = True
            EMULATE = True
    except:
        DISPLAY_VALID = False
        print("ERROR: Cannot load display modules. There will be no display output!\n\
    This script will still function as a basic flight parser and stat generator, if the environment allows.")
        time.sleep(5)

# If we invoked this script by terminal and we forgot to set any flags, set this flag.
# This affects how to handle our exit signals
if INTERACTIVE == False:
    if sys.__stdin__.isatty(): FORGOT_TO_SET_INTERACTIVE = True

try: # Attempt to load config data
    from config import (
        FLYBY_STATS_ENABLED,
        HEIGHT_LIMIT,
        RANGE,
        API_KEY,
        API_DAILY_LIMIT,
        CLOCK_24HR,
        CUSTOM_DUMP1090_LOCATION,
        CUSTOM_DUMP978_LOCATION,
        BRIGHTNESS,
        GPIO_SLOWDOWN,
        HAT_PWM_ENABLED,
        RGB_ROWS,
        RGB_COLS,
        LED_PWM_BITS
    )

except (ModuleNotFoundError, NameError): # If there's no config data
    FLYBY_STATS_ENABLED: bool = False
    HEIGHT_LIMIT = 15000
    RANGE = 2
    API_KEY = ""
    API_DAILY_LIMIT = None
    CLOCK_24HR = True
    CUSTOM_DUMP1090_LOCATION = ""
    CUSTOM_DUMP978_LOCATION = ""
    BRIGHTNESS = 100
    GPIO_SLOWDOWN = 2
    HAT_PWM_ENABLED = False
    RGB_ROWS = 32
    RGB_COLS = 64
    LED_PWM_BITS = 8
    print(f"Warning: Cannot find configuration file \'config.py\' in \'{CURRENT_DIR}\'\n\
         or settings file is missing required entries. Using default settings.")

# our global variables
general_stats: list = []
""" general dump1090 stats (updated per loop) """
relevant_planes: list = []
""" list of planes and associated stats found inside area of interest (refer to `main_loop_generator.dump1090_loop()`) """
focus_plane: str = ""
""" current plane in focus, selected by `AirplaneParser.plane_selector()` """
focus_plane_stats: dict = {}
""" extracted stats for `focus_plane` from `relevant_planes` """
focus_plane_iter: int = 0
""" variable that increments per loop when `AirplaneParser` is active """
focus_plane_ids_scratch = set()
""" scratchpad of currently tracked planes (all IDs in `relevant_planes` at current loop).
Elements can be removed if plane count > 1 due to selector algorithm """
focus_plane_ids_discard = set()
""" scratchpad of previously tracked plane IDs during the duration of `AirplaneParser`'s execution """
focus_plane_api_results = deque([None] * 25, maxlen=25)
""" Additional API-derived information for `focus_plane` and previously tracked planes from FlightAware API.
Valid keys are {`ID`, `Flight`, `Origin`, `Destination`, `Departure`} """
unique_planes_seen = set()
""" set that tracks unique hex IDs of all plane flybys in a day """
idle_data: dict = {'Flybys': "0", 'Track': "0", 'Range': "0"}
""" formatted dict for our Display driver.
`idle_data` = {`Flybys`, `Track`, `Range`} """
active_data: dict = {}
""" formatted dict for our Display driver.
`active_data` = {`Callsign`, `Origin`, `Destination`, `FlightTime`, `Altitude`, `Speed`, `Distance`, `Country`, `ActivePlanes`} or {}"""
active_plane_display: bool = False
""" which scene to put on the display. False = clock/idle, True = active plane """
rlat: float | None = None
""" our location latitude """
rlon: float | None = None
""" our location longitude """
# hashable objects for our cross-thread signaling
DATA_UPDATED: str = "updated-data"
PLANE_SELECTED: str = "plane-in-range"
DISPLAY_SWITCH: str = "reset-scene"
END_THREADS: str = "terminate"
process_time: list = [0,0,0,0]
""" for debug; [json parse, filter data, API response, format data] ms """
api_hits: list = [0,0,0,0]
""" [successful API returns, failed API returns, no data returned, cache hits] """
flyby_stats_present: bool = False
""" flag to check if we can write to `FLYBY_STATS_FILE`, initialized to False """

if (sys.version_info > (3, 0)):
    def has_key(book, key):
        return (key in book)
else:
    def has_key(book, key):
        return book.has_key(key)

# make additional use for psutil
this_process = psutil.Process()
this_process_cpu = this_process.cpu_percent(interval=None)
CORE_COUNT = os.cpu_count()
if CORE_COUNT == None:
    CORE_COUNT = 1

# =========== Program Setup I ==============
# ==========================================

def sigterm_handler(signal, frame):
    """ Shutdown worker threads and exit this program. """
    end_time = round(time.monotonic() - START_TIME, 3)
    dispatcher.send(message='', signal=END_THREADS, sender=sigterm_handler)
    os.write(sys.stdout.fileno(), str.encode(f"\n- Exit signal commanded at {datetime.datetime.now()}\n"))
    os.write(sys.stdout.fileno(), str.encode(f"  Script ran for {timedelta_clean(end_time)}\n"))
    os.write(sys.stdout.fileno(), str.encode(f"Shutting down... "))
    flyby_stats()
    os.write(sys.stdout.fileno(), b"Done.\n")
    sys.exit(0)

def register_signal_handler(loop, handler, signal, sender) -> None:
    """ Thread communication enabler. """
    def dispatcher_receive(message):
        loop.call_soon_threadsafe(handler, message)
    dispatcher.connect(dispatcher_receive, signal=signal, sender=sender, weak=False)

def probe1090() -> str | None:
    """ Determines which json exists on the system. Returns `JSON1090_LOCATION` and its base `URL` """
    locations = iter(
        [CUSTOM_DUMP1090_LOCATION,
         "http://localhost/tar1090",
         "http://localhost/skyaware",
         "http://localhost:8080",]
         )
    while True:
        json_1090 = next(locations, "nothing")
        if json_1090 == "nothing":
            return None, None
        try:
            test1 = requests.get(json_1090 + '/data/aircraft.json', timeout=0.5)
            test1.raise_for_status()
            return json_1090 + '/data/aircraft.json', json_1090
        except:
            pass

def probe978() -> str | None:
    """ Check if dump978 exists and returns its `URL` or None if not found. """
    locations = iter(
        ["http://localhost:8978",
         CUSTOM_DUMP978_LOCATION]
    )
    while True:
        json_978 = next(locations, "nothing")
        if json_978 == "nothing": break
        try:
            test1 = requests.get(json_978 + '/data/aircraft.json', timeout=0.5)
            test1.raise_for_status()
            print(f"dump978 detected as well, at \'{json_978}\'")
            return json_978 + '/data/aircraft.json'
        except:
            pass
    return None

def cls() -> None:
    """ Clear the console when using a terminal """
    os.system('cls' if os.name=='nt' else 'clear')

def timedelta_clean(timeinput: datetime) -> str:
    """ Cleans up time deltas without the microseconds. """
    delta_time = datetime.timedelta(seconds=timeinput)
    return str(delta_time).split(".")[0]

def strfdelta(tdelta, fmt='{D:02}d {H:02}h {M:02}m {S:02}s', inputtype='timedelta') -> str:
    """Convert a datetime.timedelta object or a regular number to a custom-
    formatted string, just like the stftime() method does for datetime.datetime
    objects. Sourced from https://stackoverflow.com/a/42320260

    The fmt argument allows custom formatting to be specified.  Fields can 
    include seconds, minutes, hours, days, and weeks.  Each field is optional.

    Some examples:
        '{D:02}d {H:02}h {M:02}m {S:02}s' --> '05d 08h 04m 02s' (default)
        '{W}w {D}d {H}:{M:02}:{S:02}'     --> '4w 5d 8:04:02'
        '{D:2}d {H:2}:{M:02}:{S:02}'      --> ' 5d  8:04:02'
        '{H}h {S}s'                       --> '72h 800s'

    The inputtype argument allows tdelta to be a regular number instead of the  
    default, which is a datetime.timedelta object.  Valid inputtype strings: 
        's', 'seconds', 
        'm', 'minutes', 
        'h', 'hours', 
        'd', 'days', 
        'w', 'weeks'
    """

    # Convert tdelta to integer seconds.
    if inputtype == 'timedelta':
        remainder = int(tdelta.total_seconds())
    elif inputtype in ['s', 'seconds']:
        remainder = int(tdelta)
    elif inputtype in ['m', 'minutes']:
        remainder = int(tdelta)*60
    elif inputtype in ['h', 'hours']:
        remainder = int(tdelta)*3600
    elif inputtype in ['d', 'days']:
        remainder = int(tdelta)*86400
    elif inputtype in ['w', 'weeks']:
        remainder = int(tdelta)*604800

    f = Formatter()
    desired_fields = [field_tuple[1] for field_tuple in f.parse(fmt)]
    possible_fields = ('W', 'D', 'H', 'M', 'S')
    constants = {'W': 604800, 'D': 86400, 'H': 3600, 'M': 60, 'S': 1}
    values = {}
    for field in possible_fields:
        if field in desired_fields and field in constants:
            values[field], remainder = divmod(remainder, constants[field])
    return f.format(fmt, **values)

def reset_unique_tracks() -> None:
    """ Resets the tracked planes set (schedule this) """
    time.sleep(5) # wait for hourly events to complete
    global unique_planes_seen, api_hits
    with threading.Lock():
        unique_planes_seen.clear()
        for i in range(len(api_hits)):
            api_hits[i] = 0
    return

def dump1090_check() -> None:
    """ Checks what dump1090 we have available upon startup. If we can't find it, just become a clock. """
    global DUMP1090_JSON, URL, DUMP978_JSON, DUMP1090_IS_AVAILABLE
    print("Searching for dump1090...")
    for wait in range(3):
        tries = 3 - wait
        DUMP1090_JSON, URL = probe1090()
        if DUMP1090_JSON is not None:
            print(f"Found dump1090 at \'{DUMP1090_JSON}\'")
            DUMP1090_IS_AVAILABLE = True
            break
        else:
            print(f"Could not find dump1090.json. dump1090 may not be loaded yet. Waiting 10 seconds and trying {tries} more time(s).")
            time.sleep(10)

    if DUMP1090_JSON == None:
        DUMP1090_IS_AVAILABLE = False
        if DISPLAY_VALID == True:
            print("Error: dump1090 not found. This will just be a cool-looking clock until this program is restarted.")
        else:
            print("Error: dump1090 not found. Additionally, screen resources are missing.\n\
       This script may not be useful until these issues are corrected.")
    DUMP978_JSON = probe978() # we don't wait for this one as it's usually not present

def read_1090_config() -> None:
    """ Gets us our location, if it is configured in dump1090. """
    global rlat, rlon
    if DUMP1090_IS_AVAILABLE == False: return
    try:
        with closing(urlopen(URL + '/data/receiver.json', None, LOOP_INTERVAL * 0.75)) as receiver_file:
            receiver = json.load(receiver_file)
        with threading.Lock():
            if has_key(receiver,'lat'): #if location is set
                rlat_last = rlat
                rlon_last = rlon
                if receiver['lat'] != rlat_last or receiver['lon'] != rlon_last:
                    rlat = float(receiver['lat'])
                    rlon = float(receiver['lon'])
                    print(f"Info: Location updated. ({rlat}, {rlon})")
            else:
                rlat = rlon = None
                print("Warning: Location has not been set! This program will not be able to determine any nearby planes or calculate range!\n\
         Please set location in dump1090 to disable this message.")
    except:
        print("Error: Cannot load receiver config.")
    return

def schedule_thread() -> None:
    """ Our schedule runner """
    while True:
        schedule.run_pending()
        time.sleep(1)

def configuration_check() -> None:
    """ Basic configuration checker """
    global RANGE, HEIGHT_LIMIT, RGB_COLS, RGB_ROWS, FLYBY_STATS_ENABLED
    valid_rgb_sizes = [16, 32, 64]
    if RGB_ROWS not in valid_rgb_sizes or RGB_COLS not in valid_rgb_sizes:
        print(f"Warning: selected RGB dimension ({RGB_ROWS}x{RGB_COLS}) is not a valid size.\n\
         Setting values to default (32x64).")
        RGB_ROWS = 32
        RGB_COLS = 64

    if NOFILTER == False:
        # set hard limits for range
        if RANGE > 20:
            print(f"Warning: desired range ({RANGE}) is out of bounds. Limiting to 20.")
            RANGE = 20
        elif RANGE < 0.2:
            print(f"Warning: desired range ({RANGE}) is too low. Limiting to 0.2.")
            RANGE = 0.2

        height_warning = f"Warning: desired height cutoff ({HEIGHT_LIMIT}) is"
        if HEIGHT_LIMIT >= 275000:
            print(f"{height_warning} beyond the theoretical limit for flight. Setting to a reasonable value (60000).")
            HEIGHT_LIMIT = 60000
        elif HEIGHT_LIMIT > 60000 and HEIGHT_LIMIT < 275000:
            print(f"{height_warning} beyond typical aviation flight levels. Limiting to 60000.")
            HEIGHT_LIMIT = 60000
        elif HEIGHT_LIMIT <= 0:
            print(f"{height_warning} ground level or underground.\n\
            Planes won't be doing the thing planes do at that point (flying). Setting to a reasonable value (5000)")
            HEIGHT_LIMIT = 5000
        elif HEIGHT_LIMIT > 0 and HEIGHT_LIMIT < 100:
            print(f"{height_warning} too low. Are planes landing on your house? \
            Setting to a reasonable value (5000)")
        del height_warning

    else:
        RANGE = 1000
        HEIGHT_LIMIT = 275000

    if API_KEY:
        print("API Key present, API will be used.")
    else:
        print("No API Key present. Additional airplane info will not be available.")

def match_commandline(command_search: str, process_name: str) -> list:
    """ Find all processes associated with a command line and process name that matches the given inputs.
    Returns a list of dictionaries of matching processes.
    Perfect for making sure only a single running instance of this script is allowed. """
    list_of_processes = []
 
    # iterate over all running processes
    for proc in psutil.process_iter():
       try:
           pinfo = proc.as_dict(attrs=['pid', 'name', 'create_time'])
           cmdline = proc.cmdline()
           # check if process name contains the given string in its command line
           if any(command_search in position for position in cmdline) and process_name in pinfo['name']:
               list_of_processes.append(pinfo)
       except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
           pass
 
    return list_of_processes

# =========== Program Setup II =============
# ==========================================

def flyby_stats() -> None:
    """
    If `FLYBY_STATS_ENABLED` is true, write the gathered stats from our flybys to a csv file. 
    When this is run for the first time, it will check if `FLYBY_STATS_FILE` exists and sets appropriate flags.
    If `FLYBY_STATS_FILE` is valid, subsequent calls to this function will append data to the end of it.
    This function assumes it will be called hourly to keep track of stats thoughout the day.
    Written values are accumulative and are reset at midnight.
    """
    global flyby_stats_present, FLYBY_STATS_ENABLED
    if FLYBY_STATS_ENABLED == False:
        return
    header = "Date,Number of flybys,API calls (successful),API calls (failed),API calls (empty)\n"
    if FLYBY_STATS_FILE.is_file() and flyby_stats_present == False:
        with open(FLYBY_STATS_FILE, 'r') as stats: # check if the file has a valid header
            head = next(stats)
            if head == header:
                flyby_stats_present = True
                print(f"Flyby stats file \'{FLYBY_STATS_FILE}\' is present.")
            # elif head == "":
            #     with open(FLYBY_STATS_FILE, 'w') as stats:
            #         stats.write(header)
            #     print(f"A new flyby stats file \'{FLYBY_STATS_FILE}\' was created.")
            #     flyby_stats_present = True
            else:
                print(f"Error: header in \'{FLYBY_STATS_FILE}\' is incorrect or has been modifed. Stats will not be saved.")
                FLYBY_STATS_ENABLED = False

        # load in last line of stats file, check if today's the current date, and re-populate our running stats
        if flyby_stats_present == True:
            with open(FLYBY_STATS_FILE, 'rb') as f:
                try:  # catch OSError in case of a one line file 
                    f.seek(-2, os.SEEK_END)
                    while f.read(1) != b'\n':
                        f.seek(-2, os.SEEK_CUR)
                except OSError:
                    f.seek(0)
                last_line = f.readline().decode()
            date_now_str = datetime.datetime.now().strftime('%Y-%m-%d')
            last_date = (last_line.split(",")[0]).split(" ")[0] # splitting strftime('%Y-%m-%d %H:%M')
            if date_now_str == last_date:
                global api_hits, unique_planes_seen
                planes_seen = int(last_line.split(",")[1])
                api_hits[0] = int(last_line.split(",")[2])
                api_hits[1] = int(last_line.split(",")[3])
                api_hits[2] = int(last_line.split(",")[4])
                for i in range(planes_seen): # fill the set with filler values, we don't recall the last contents of `unique_planes_seen`
                    unique_planes_seen.add(i+1)
                print(f"Successfully reloaded last written data for {date_now_str}.")
        return
    
    elif not FLYBY_STATS_FILE.is_file():
        try:
            if os.name=='posix':
                os.mknod(FLYBY_STATS_FILE)
                os.chmod(FLYBY_STATS_FILE, 0o777)
            with open(FLYBY_STATS_FILE, 'w') as stats:
                stats.write(header)
            print(f"No Flyby stats file was found. A new flyby stats file \'{FLYBY_STATS_FILE}\' was created.")
            flyby_stats_present = True
            return
        except:
            print(f"Error: Cannot write to \'{FLYBY_STATS_FILE}\'. Stats will not be saved.")
            FLYBY_STATS_ENABLED = False
            return

    if flyby_stats_present == True:
        date_now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        try:
            with open(FLYBY_STATS_FILE, 'a') as stats:
                stats.write(f"{date_now_str},{len(unique_planes_seen)},{api_hits[0]},{api_hits[1]},{api_hits[2]}\n")
#             print(f"({date_now_str}) - {len(unique_planes_seen)} flybys so far today. \
# {api_hits[0]}/{api_hits[0]+api_hits[1]} successful API calls, of which {api_hits[2]} returned no data.")
        except:
            print(f"Error: Cannot write to \'{FLYBY_STATS_FILE}\'. Data for {date_now_str} has been lost.")
    return

def print_to_console() -> None:
    """ This is for testing/viewing internal logic. Note: this is summoned by `AirplaneParser`
    as it is expected that all the variables will have their end-of-loop values written at the end of execution. """
    global this_process_cpu
    plane_count = len(relevant_planes)
    run_time = time.monotonic() - START_TIME
    time_print = str(datetime.datetime.now()).split(".")[0]

    cls()
    print(f"===== FlightGazer Console Output ===== Time now: {time_print} | Runtime: {timedelta_clean(run_time)}")
    if DUMP1090_IS_AVAILABLE == False:
        print("********** dump1090 did not successfully load. There will be no data! **********\n")
    if (rlat == None or rlon == None) and NOFILTER == False:
        print("********** Location is not set! No airplane information will be shown! **********\n")
    if NOFILTER == False:
        print(f"Filters enabled: <{RANGE}nmi, <{HEIGHT_LIMIT}ft\n(* indicates in focus, - indicates focused previously)")
    else:
        print("******* No Filters mode enabled. All planes with locations detected by dump1090 shown. *******\n")
    if focus_plane_iter != 0:
        print(f"[Inside focus loop {focus_plane_iter}, watching: \'{focus_plane}\']\n", flush=True)
        print(f"Plane scratchpad: {focus_plane_ids_scratch}")

    for a in range(plane_count):
        if focus_plane_ids_discard:
            if relevant_planes[a]['ID'] in focus_plane_ids_discard: print("- ", end='', flush=True)
        if focus_plane == relevant_planes[a]['ID']: print("* ", end='', flush=True)
        print("[{a:03d}] {flight} ({iso}, {id}) Speed: {gs}kt Alt: {alt}ft Distance: {direc}{distance:.1f}nmi"
            .format(flight=relevant_planes[a]['Flight'],
                    iso=relevant_planes[a]['Country'],
                    gs=relevant_planes[a]['Speed'],
                    alt=relevant_planes[a]['Altitude'],
                    distance=relevant_planes[a]['Distance'],
                    direc=relevant_planes[a]['Direction'],
                    id=relevant_planes[a]['ID'],
                    a=a+1
                    )
                )
        
    for i in range(len(focus_plane_api_results)): # only shows if API has something to show
        try:
            if focus_plane_api_results[-i-1] is not None and focus_plane == focus_plane_api_results[-i-1]['ID']:
                api_flight = focus_plane_api_results[-i-1]['Flight']
                api_orig = focus_plane_api_results[-i-1]['Origin']
                if api_orig == None: api_orig = "?"
                api_dest = focus_plane_api_results[-i-1]['Destination']
                if api_dest == None: api_dest = "?"
                api_dpart_time = focus_plane_api_results[-i-1]['Departure']
                if api_dpart_time is not None:
                    api_dpart_delta = (datetime.datetime.now(datetime.timezone.utc) - api_dpart_time)
                    api_dpart_delta = str(api_dpart_delta).split(".")[0]
                else:
                    api_dpart_delta = "?"
                print(f"\nAPI results for {api_flight}: {api_orig} -> {api_dest}, {api_dpart_delta} flight time")
                break
        except: # if we bump into None or something else
            break

    print(f"\n> dump1090 response {process_time[0]} ms | \
Processing {process_time[1]} ms | Display formatting {process_time[3]} ms | Last API response {process_time[2]} ms")
    print(f"> Detected {general_stats['Tracking']} plane(s), {plane_count} plane(s) in range, max range: {general_stats['Range']}nmi")
    if API_KEY:
        print(f"> API stats for today: {api_hits[0]} success, {api_hits[1]} fail, {api_hits[2]} no data, {api_hits[3]} cache hits")
    print(f"> Total flybys today: {len(unique_planes_seen)}")
    current_memory_usage = psutil.Process().memory_info().rss
    this_process_cpu = this_process.cpu_percent(interval=None)
    print(f"> CPU & memory usage: {round(this_process_cpu / CORE_COUNT, 3)}% overall CPU | {round(current_memory_usage / 1048576, 3)}MiB")

def main_loop_generator() -> None:
    """ Our main `LOOP` generator. Only generates/publishes data for subscribers to interpret.
    (an homage to Davis Instruments `LOOP` packets for their weather stations) """

    def relative_direction(lat0: float, lon0: float, lat1: float, lon1: float) -> str:
        """ Gets us the plane's relative location in respect to our location. 
        Sourced from here: https://gist.github.com/RobertSudwarts/acf8df23a16afdb5837f?permalink_comment_id=3070256#gistcomment-3070256 """
        d = math.atan2((lon1 - lon0), (lat1 - lat0)) * (180 / math.pi)
        dirs = ['N ', 'NE', 'E ', 'SE', 'S ', 'SW', 'W ', 'NW'] # cut down directions and add spaces for output
        # dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        ix = round(d / (360. / len(dirs)))
        return dirs[ix % len(dirs)]
    
    def greatcircle(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
        """ Calculates distance between two points on Earth based on their latitude and longitude (in nautical miles) """
        lat0 = lat0 * math.pi / 180.0
        lon0 = lon0 * math.pi / 180.0
        lat1 = lat1 * math.pi / 180.0
        lon1 = lon1 * math.pi / 180.0
        # use Earth radius in nautical miles
        return 3440 * math.acos(math.sin(lat0) * math.sin(lat1) + math.cos(lat0) * math.cos(lat1) * math.cos(abs(lon1 - lon0)))

    def dump1090_heartbeat() -> list | None:
        """ Checks if dump1090 service is up and returns the relevant json file(s). If service is down/times out, returns None. """
        try:
            with closing(urlopen(DUMP1090_JSON, None, LOOP_INTERVAL * 0.75)) as aircraft_file:
                aircraft_data = json.load(aircraft_file)
            if DUMP978_JSON is not None:
                with closing(urlopen(DUMP978_JSON, None, LOOP_INTERVAL * 0.75)) as aircraft_file2:
                    aircraft_data2 = json.load(aircraft_file2)
                    aircraft_data['aircraft'].extend(aircraft_data2['aircraft']) # append dump978 json into dump1090 data
            return aircraft_data
        except:
            return None

    def dump1090_loop(dump1090_data: list) -> dict | list:
        """ Our dump1090 json parser. Must be fed by a valid `dump1090_heartbeat()` response. Returns a dictionary and a list.
        - dictionary: general stats to be updated per loop.
            - Tracking = total planes being tracked at current time
            - Range = maximum range of tracked planes from your location (in nautical miles)
        - list: list of nested dictionaries that describes each plane found within `HEIGHT_LIMIT` and `RANGE` and updates per loop.
        If no planes are found or location is not set, this will return an empty list.
            - ID: ICAO hex of airplane
            - Flight: Callsign (falls back to registration and finally hex)
            - Country: Returns two letter ISO code based on ICAO hex
            - Altitude: Plane's altitude in feet. Returns 0 if can't be determined or if the plane is on the ground.
            - Speed: Plane's ground speed in knots. Returns 0 if can't be determined.
            - Distance: Plane's distance from your location in nautical miles. Returns 0 if location is not defined.
            - Direction: Cardinal direction of plane in relation to your location. Returns an empty string if location is not defined.
        """
        # inspired by https://github.com/wiedehopf/graphs1090/blob/master/dump1090.py
        # refer to https://github.com/wiedehopf/readsb/blob/dev/README-json.md on relevant json keys

        aircraft_data = dump1090_data
        total = 0
        max_range = 0
        ranges = []
        planes = []
        
        try:
            for a in aircraft_data['aircraft']:
                seen_pos = a.get('seen_pos')
                # seen_pos = a.get('seen') # use last seen versus last seen position
                # filter planes that have valid tracking data and were seen recently
                if seen_pos == None or seen_pos > 60:
                    continue
                total +=1
                if rlat is not None and rlon is not None:
                    distance = greatcircle(rlat, rlon, a.get('lat'), a.get('lon'))
                else:
                    distance = 0
                ranges.append(distance)
                if (NOFILTER == False and (distance < RANGE and distance > 0)) or\
                    NOFILTER == True:
                    alt_baro = a.get('alt_baro')
                    if alt_baro == "ground": alt_baro = 0
                    if alt_baro is None or alt_baro < HEIGHT_LIMIT:
                        hex = a.get('hex')
                        if hex is None: hex = "?"
                        # lat = a.get('lat')
                        # lon = a.get('lon')
                        # rssi = a.get('rssi')
                        gs = a.get('gs')
                        flight = a.get('flight')
                        if rlat is not None:
                            direc = relative_direction(rlat, rlon, a.get('lat'), a.get('lon'))
                        else:
                            direc = ""
                        iso_code = flags.getICAO(hex).upper()
                        registration = registrations.registration_from_hexid(hex)
                        if gs is None: gs = 0
                        if flight is None:
                            # fallback to registration, then ICAO hex
                            if registration is not None:
                                flight = registration
                            else:
                                flight = hex
                        else:
                            flight = flight.strip() # callsigns have ending whitespace; we need to remove for polling the API
                        if alt_baro is None: alt_baro = 0
                        planes.append(
                            {
                            "ID": hex,
                            "Flight": flight,
                            "Country": iso_code,
                            "Altitude": alt_baro,
                            "Speed": gs,
                            "Distance": distance,
                            "Direction": direc
                            }
                        )
                        unique_planes_seen.add(hex)

            if not ranges:
                max_range = 0
            else:
                max_range = round(max(ranges), 1)

            current_stats = {"Tracking": total, "Range": max_range}

        except: # just reuse the last data if an edge case is encountered
            current_stats = general_stats
            planes = relevant_planes

        return current_stats, planes
    
    def loop():
        """ Do the loop """
        global general_stats, relevant_planes, unique_planes_seen, process_time
        while True:
            try:
                loadingtime = time.perf_counter()
                dump1090_data = dump1090_heartbeat()
                if dump1090_data is None:
                    general_stats = {'Tracking': 0, 'Range': 0}
                    if DUMP1090_IS_AVAILABLE == True: raise TimeoutError
                process_time[0] = round((time.perf_counter() - loadingtime)*1000, 3)
                start_time = time.perf_counter()
                if DUMP1090_IS_AVAILABLE == True:
                    with threading.Lock():
                        general_stats, relevant_planes = dump1090_loop(dump1090_data)
                process_time[1] = round((time.perf_counter() - start_time)*1000, 3)

                dispatcher.send(message='', signal=DATA_UPDATED, sender=main_loop_generator)
                time.sleep(LOOP_INTERVAL) # our main loop polling time

            except TimeoutError:
                cls()
                print("Dump1090 service timed out, retrying...")
                time.sleep(LOOP_INTERVAL)
                continue

            except (SystemExit, KeyboardInterrupt):
                print("\nLoop ended by external control.")
                return

            except:
                cls()
                print("Error: LOOP thread caught an exception. Trying again...")
                time.sleep(LOOP_INTERVAL)
                continue

    # Enter here
    loop()

class AirplaneParser:
    """ When there are planes in `relevant_planes`, continuously parses plane list, determines active plane, then triggers API fetcher.
    This thread is awoken every time `main_loop_generator.dump1090_loop()` updates data. """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        register_signal_handler(self.loop, self.plane_selector, signal=DATA_UPDATED, sender=main_loop_generator)
        register_signal_handler(self.loop, self.end_thread, signal=END_THREADS, sender=sigterm_handler)
        self.run_loop()
   
    def plane_selector(self, message):
        """ Select a plane! """
        global focus_plane, focus_plane_stats, focus_plane_iter, focus_plane_ids_scratch, focus_plane_ids_discard, process_time
        plane_count = len(relevant_planes)
        get_plane_list: list = []
        focus_plane_i: str = ""

        def select():
            """ 
            The following selector algorithm is rather naive, but it works for occurences when there is more than one plane in the area
            and we want to put some effort into trying to go through all of them without having to flip back and forth constantly.
            It is designed this way to minimize API calls (it can get real expensive real quick if you're nearby a major international airport).
            Additionally, it avoids the complications associated with trying to use a queue to handle `relevant_planes` per data update.
            The algorithm keeps track of already tracked planes and (tries to) switch the focus to planes that haven't been tracked yet.
            `RANGE` should be relatively small giving us less possible concurrent planes to handle at a time, as the more planes are in the area,
            the higher the chance some planes will not be tracked whatsoever due to the latching time.
            """
            """
            Programmer's notes: A truly smarter way would be reading the current range and altitude of each plane,
            calculating the magnitude of its change (eg. is it getting closer or farther), and translating this into a priority.
            ex: if plane1 is 0.5nmi away and getting closer, keep focus on this plane as plane2 enters `RANGE`. Once plane1 starts
            moving away, then we can focus on plane2. This approach can get much more complicated as the amount of planes increases
            while keeping us from constantly switching (for the case of multiple planes flying in parallel).
            There is likely some kind of method or algorithm out there that could solve this. If you're not me and you're reading this comment block,
            reach out, I want to see your take. - WeegeeNumbuh1 (Nov. 2024)
            """
            global focus_plane, focus_plane_ids_discard, focus_plane_ids_scratch
            with threading.Lock():
                focus_plane_ids_discard.add(focus_plane_i) # add previously assigned focus plane to scratchpad of planes to ignore
                discard_list = list(focus_plane_ids_discard)
                for i in range(len(discard_list)): # remove all previously focused planes from the global list
                    focus_plane_ids_scratch.discard(discard_list[i])
                scratch_list = list(focus_plane_ids_scratch)
                if len(focus_plane_ids_scratch) > 0:
                    focus_plane = random.choice(scratch_list) # get us the next plane from all remaining planes that were not tracked previously
                elif len(focus_plane_ids_scratch) == 0: # when we have cycled through all planes available, fall back to the first plane in list
                    focus_plane = get_plane_list[0]

        start_time = time.perf_counter()
        focus_plane_i = focus_plane # get previously assigned focus plane into this loop's copy

        if NOFILTER == False:
            if plane_count > 0:
                with threading.Lock():
                    focus_plane_ids_scratch.clear()
                    for a in range(plane_count):
                        get_plane_list.append(relevant_planes[a]['ID']) # current planes in this loop 
                        focus_plane_ids_scratch.add(relevant_planes[a]['ID']) # add the above to the global list (rebuilds each loop)
                            
                focus_plane_iter += 1

                # if this block of code is awoken, get the first plane from this loop's copy and declare it our focus plane
                if not focus_plane_i:
                    focus_plane = get_plane_list[0]
                
                # for the case when the last focus plane leaves the area and new ones appear on this refresh
                # note this will never run if the above block executed
                if focus_plane not in get_plane_list:
                    focus_plane = random.choice(get_plane_list)

                # control our latching time based on how many planes are present in the area;
                # if a new plane enters the area or the number of planes changes,
                # only switch focus plane when modulo hits zero.
                # int(time_in_seconds // LOOP_INTERVAL)
                if plane_count == 2 and focus_plane_iter % int(30 // LOOP_INTERVAL) == 0:
                    select()
                if plane_count == 3 and focus_plane_iter % int(20 // LOOP_INTERVAL) == 0:
                    select()
                if plane_count > 3 and focus_plane_iter % int(15 // LOOP_INTERVAL) == 0:
                    select()
                
                # finally
                with threading.Lock():
                    for i in range(len(relevant_planes)): # find our focus plane in `relevant_planes`
                        if focus_plane == relevant_planes[i]['ID']:
                            focus_plane_stats = relevant_planes[i]
                            break

                # if this thread changed the focus plane, fire up the API fetcher
                if focus_plane_i != focus_plane:
                    dispatcher.send(message=focus_plane, signal=PLANE_SELECTED, sender=AirplaneParser.plane_selector)

            else: # when there are no planes
                if focus_plane: # clean-up variables
                    with threading.Lock():
                        focus_plane = ""
                        focus_plane_iter = 0
                        focus_plane_stats.clear()
                        focus_plane_ids_scratch.clear()
                        focus_plane_ids_discard.clear()
        
        with threading.Lock():
            process_time[1] = round(process_time[1] + (time.perf_counter() - start_time)*1000, 3)
        
        if INTERACTIVE:
            print_to_console()

    def run_loop(self):
        def keep_alive():
            self.loop.call_later(1, keep_alive)
        keep_alive()
        self.loop.run_forever()

    def end_thread(self, message):
        self.loop.stop()

class APIFetcher:
    """ Gets us plane information via FlightAware API. """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        register_signal_handler(self.loop, self.get_API_results, signal=PLANE_SELECTED, sender=AirplaneParser.plane_selector)
        register_signal_handler(self.loop, self.end_thread, signal=END_THREADS, sender=sigterm_handler)
        self.run_loop()

    def get_API_results(self, message):
        """ The real meat and potatoes for this class. Will append a dict to `focus_plane_api_results` with any attempt to query the API. """
        if not API_KEY: return
        if NOFILTER == True: return
        global process_time, focus_plane_api_results, api_hits
        # get us our dates to narrow down how many results the API will give us
        date_now = datetime.datetime.now()
        time_delta_yesterday = date_now - datetime.timedelta(days=1)
        date_yesterday_iso = time_delta_yesterday.astimezone().replace(microsecond=0).isoformat()
        date_tomorrow = date_now + datetime.timedelta(days=1)
        date_tomorrow_iso = date_tomorrow.astimezone().replace(microsecond=0).isoformat()
        origin = None
        destination = None
        departure_time = None

        flight_id = ""
        for i in range(len(relevant_planes)): # find our focus plane in `relevant_planes`
            if focus_plane == relevant_planes[i]['ID']:
                flight_id = relevant_planes[i]['Flight']
                break

        # if for some reason there is no flight ID, don't bother trying to query the API
        if not flight_id or flight_id == '?': return

        # check if we already have results
        for i in range(len(focus_plane_api_results)):
            try:
                if focus_plane_api_results[-i-1] is not None and\
                focus_plane == focus_plane_api_results[-i-1]['ID']: # cache hit: no need to query the API; reads deque from right to left
                    api_hits[3] += 1
                    return
            except: # if we bump into None or something else
                break

        # this is for limiting API calls per day for testing; just bumps up the "no data" count
        if API_DAILY_LIMIT is not None and api_hits[0] == API_DAILY_LIMIT:
            api_hits[2] += 1
            return

        auth_header = {'x-apikey':API_KEY, 'Accept':"application/json; charset=UTF-8"}
        query_string = (API_URL
                        + f"flights/{flight_id}"
                        + "?start=" + urllib.parse.quote(date_yesterday_iso)
                        + "&end=" + urllib.parse.quote(date_tomorrow_iso)
                        + "&max_pages=1"
                        )
        
        try:
            start_time = time.perf_counter()
            response = requests.get(query_string, headers=auth_header, timeout=5)
            process_time[2] = round((time.perf_counter() - start_time)*1000, 3)
            response.raise_for_status
            if response.status_code == 200: # check if service to the API call was valid
                response_json = response.json()
                # API reference -> https://www.flightaware.com/aeroapi/portal/documentation#get-/flights/-ident-
                if response_json['flights']: # if no results (ex: invalid flight_id or plane is blocked from tracking) this key will not exist
                    api_hits[0] += 1
                    for a in range(len(response_json['flights'])):
                        if "En Route" in response_json['flights'][a]['status']: # check we're reading current flight information
                            # check if these subkeys exist, if not, just return None
                            try:
                                # we optimally want the 3 letter airport codes
                                # cascade through these keys until we have something
                                origin: str | None = response_json['flights'][a]['origin']['code_lid']
                                if origin is None or origin == 'null':
                                    origin = response_json['flights'][a]['origin']['code_iata']
                                if origin is None or origin == 'null':
                                    origin = response_json['flights'][a]['origin']['code']
                                if origin is None or origin == 'null': origin = None
                            except: origin = None
                            try:
                                destination: str | None = response_json['flights'][a]['destination']['code_lid']
                                if destination is None or destination == 'null':
                                    destination = response_json['flights'][a]['destination']['code_iata']
                                if destination is None or destination == 'null':
                                    destination = response_json['flights'][a]['destination']['code']
                                if destination is None or destination == 'null': destination = None
                            except: destination = None
                            try:
                                depart_iso: str | None = response_json['flights'][a]['actual_off']
                                if depart_iso is None or depart_iso == 'null':
                                    departure_time = None
                                else:
                                    departure_time = depart_iso[:-1] + "+00:00" # API returns UTC time; need to format for .fromisoformat()
                                    departure_time = datetime.datetime.fromisoformat(departure_time)
                            except: departure_time = None
                            break
                else:
                    api_hits[2] += 1
            else:
                raise Exception
        except:
            api_hits[1] += 1
        finally:
            # special case when the API returns a coordinate instead of an airport
            # format is: "L 000.00000 000.00000" (no leading zeros, ordered latitude longitude)
            if origin is not None and origin.startswith("L "):
                orig_coord = origin[2:].split(" ")
                lat = float(orig_coord[0])
                lon = float(orig_coord[1])
                if lat >= 0: lat_str = "N"
                elif lat <0: lat_str = "S"
                if lon >= 0: lon_str = "E"
                elif lon <0: lon_str = "W"
                origin = str(abs(round(lat, 1))) + lat_str
                # Exploit the fact that since we are looking at a position-only flight there will be no known destination beforehand.
                # We replace the destination with the longitude instead for space reasons (worst case string length: 5 lat, 6 lon)
                if destination is None:
                    destination = str(abs(round(lon, 1))) + lon_str

            api_results = {'ID':focus_plane, 'Flight':flight_id, 'Origin':origin, 'Destination':destination, 'Departure':departure_time}
            with threading.Lock():
                focus_plane_api_results.append(api_results)

    def run_loop(self):
        def keep_alive():
            self.loop.call_later(1, keep_alive)
        keep_alive()
        self.loop.run_forever()

    def end_thread(self, message):
        self.loop.stop()

class DisplayFeeder:
    """ Parses our global variables for our display driver. The display itself should be dumb; we do the processing here
    much like how `print_to_console()` displays its data. """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        register_signal_handler(self.loop, self.data_packet, signal=DATA_UPDATED, sender=main_loop_generator)
        register_signal_handler(self.loop, self.end_thread, signal=END_THREADS, sender=sigterm_handler)
        self.run_loop()

    def data_packet(self, message):
        """ Every time `main_loop_generator()` fires, grab a copy of our global variables and convert them
        into a coalesed data packet for the Display. We also control scene switching here and which scene to display.
        Outputs two dicts, `idle_stats` and `active_stats`.
        `idle_stats` = {'Flybys', 'Track', 'Range'}
        `active_stats` = {'Callsign', 'Origin', 'Destination', 'FlightTime', 'Altitude', 'Speed', 'Distance', 'Country', 'ActivePlanes'} or {}.
        All values are formatted as strings. """
        global idle_data, active_data, active_plane_display
        displayfeeder_start = time.perf_counter()
        if active_data: # check if active_data exists and do a comparison after we're done
            active_data_i = True
        else:
            active_data_i = False
        # idle_stats
        total_flybys = "0"
        total_planes = "0"
        current_range = "0"
        if general_stats:
            total_flybys = str(len(unique_planes_seen))
            total_planes = str(general_stats['Tracking'])
            current_range_i = general_stats['Range']
            if current_range_i >= 100: # just get us the integer values
                current_range = str(round(current_range_i, 0))[:3]
            elif current_range_i >= 0 or current_range_i < 100:
                current_range = str(current_range_i)

        idle_stats = {
            'Flybys': total_flybys,
            'Track': total_planes,
            'Range': current_range,
        }

        # active_stats
        filler_text = "---"
        active_stats = {}
        if focus_plane:
            relevant_plane_count = len(relevant_planes)
            # find our focus plane in relevant_planes
            flight_name = ""
            iso = ""
            gs = ""
            alt = ""
            distance = ""
            for a in range(relevant_plane_count):
                if focus_plane == relevant_planes[a]['ID']:
                    flight_name = str(relevant_planes[a]['Flight'])
                    iso = str(relevant_planes[a]['Country'])
                    # speed readout is limited to 4 characters;
                    # if speed >= 100, truncate to just the integers
                    gs_i = str(round(relevant_planes[a]['Speed'], 1))
                    if len(gs_i) <= 4: gs = gs_i
                    elif len(gs_i) > 4: gs = gs_i[:3]
                    alt = str(relevant_planes[a]['Altitude'])
                    # distance readout is limited to 5 characters (2 direction, 3 value);
                    # if distance >= 10, just get us the integers
                    dist_i = round(relevant_planes[a]['Distance'], 1)
                    if dist_i >= 0 and dist_i < 10: dist = str(dist_i)
                    elif dist_i >= 10 and dist_i < 100: dist = str(dist_i)[:2]
                    elif dist_i > 100: dist = str(dist_i)[:3]
                    else: dist = ""
                    distance = str(relevant_planes[a]['Direction']) + dist

            # get us our API results from focus_plane_api_results
            api_orig = filler_text
            api_dest = filler_text
            api_dpart_delta = filler_text
            for i in range(len(focus_plane_api_results)):
                try:
                    if focus_plane_api_results[-i-1] is not None and focus_plane == focus_plane_api_results[-i-1]['ID']:
                        api_orig = focus_plane_api_results[-i-1]['Origin']
                        if api_orig is None: api_orig = filler_text
                        api_dest = focus_plane_api_results[-i-1]['Destination']
                        if api_dest is None: api_dest = filler_text
                        api_dpart_time = focus_plane_api_results[-i-1]['Departure']
                        if api_dpart_time is not None:
                            api_dpart_delta = strfdelta((datetime.datetime.now(datetime.timezone.utc) - api_dpart_time), "{H}h{M:02}m")
                        else:
                            api_dpart_delta = filler_text
                        break
                except: # if we bump into None or something else
                    break

            active_stats = {
                'Callsign': flight_name,
                'Origin': api_orig,
                'Destination': api_dest,
                'FlightTime': api_dpart_delta,
                'Altitude': alt,
                'Speed': gs,
                'Distance': distance,
                'Country': iso,
                'ActivePlanes': str(relevant_plane_count),
            }
        with threading.Lock():
            if NOFILTER == False:
                if active_stats: active_plane_display = True
                else: active_plane_display = False
            else:
                active_plane_display = False

            if (active_stats == {}) != active_data_i:
                dispatcher.send(message='', signal=DISPLAY_SWITCH, sender=DisplayFeeder.data_packet) # as of now this isn't in use

            idle_data = idle_stats
            active_data = active_stats
            process_time[3] = round((time.perf_counter() - displayfeeder_start) * 1000, 3)
        # return idle_stats, active_stats
    
    def run_loop(self):
        def keep_alive():
            self.loop.call_later(1, keep_alive)
        keep_alive()
        self.loop.run_forever()

    def end_thread(self, message):
        self.loop.stop()

# ========== Display Superclass ============
# ==========================================

class Display(
    Animator,
):
    """ Our Display driver. """
    """ Programmer's notes:
    Adapted from Colin Waddell's approach to work with this program's data setup.

    In his original design, all the display "scenes" are integrated with one another via multiple inheritance in what I consider
    a "walled-garden" approach: one module `Overhead()` served as the data generator that controlled which
    scenes were on the current canvas, including the relevant data to display. The design for that module was such that
    it would pull data from the original API and insert the data within `Display()`'s `self` instance.
    Additionally, `Overhead()` would generate a queue of data for other modules/scenes to parse through, and once
    all the data had been read out, we switch back to being a clock.

    We are using a queue-less and dynamic approach; the displayed data can switch whenever based on the current data.
    Moreover, our data exists in global variables; we would not be able to break out the scenes in this code into their own modules.
    Hence, we're basically going to shove all of the scenes inspired by Waddell, including our added stuff, as part of this single class
    and let `DisplayFeeder` control what we do.

    n.b.: Use the @Animator decorator to control both how often elements update and our logic evaluations. """
    def __init__(self):

        # Setup Display
        options = RGBMatrixOptions()
        options.hardware_mapping = "adafruit-hat-pwm" if HAT_PWM_ENABLED else "adafruit-hat"
        options.rows = RGB_ROWS
        options.cols = RGB_COLS
        options.chain_length = 1
        options.parallel = 1
        options.row_address_type = 0
        options.multiplexing = 0
        options.brightness = BRIGHTNESS
        options.pwm_lsb_nanoseconds = 130
        options.led_rgb_sequence = "RGB"
        options.pixel_mapper_config = ""
        options.show_refresh_rate = 0
        options.pwm_bits = LED_PWM_BITS
        options.gpio_slowdown = GPIO_SLOWDOWN
        options.disable_hardware_pulsing = False if HAT_PWM_ENABLED else True
        # setting the next option to True affects our ability to write to our stats file if set and present
        # this bug took awhile to figure out, lmao
        options.drop_privileges = False if flyby_stats_present else True
        self.matrix = RGBMatrix(options=options)

        # Setup canvas
        self.canvas = self.matrix.CreateFrameCanvas()
        self.canvas.Clear()

        # Data to watch
        """ The below is absolutely important; all scenes look at this property to control their visibility. """
        self.active_plane_display = active_plane_display
        self._last_active_state = False

        # Set up previous-data buffers for *all* elements that change their value
        # clock elements
        self._last_time = None
        self._last_date = None
        self._last_day = None
        self._last_seconds = None
        self._last_ampm = None
        # idle stats
        self._last_flybys = None
        self._last_track = None
        self._last_range = None
        # active stats (plane info)
        self._last_callsign = None
        self._last_origin = None
        self._last_destination = None
        self._last_flighttime = None
        self._last_altitude = None
        self._last_speed = None
        self._last_distance = None
        self._last_country = None
        self._last_activeplanes = None

        # Initalize animator
        super().__init__()

        # Overwrite any default settings from Animator
        self.delay = frames.PERIOD

    @Animator.KeyFrame.add(frames.PER_SECOND * 0.1)
    def scene_switch(self, count):
        if self._last_active_state != active_plane_display:
            self.active_plane_display = active_plane_display
            self.reset_scene()
        self._last_active_state = self.active_plane_display

    def draw_square(self, x0:int, y0:int, x1:int, y1:int, color):
        for x in range(x0, x1):
            _ = graphics.DrawLine(self.canvas, x, y0, x, y1, color)

    @Animator.KeyFrame.add(0)
    def clear_screen(self):
        # First operation after a screen reset
        self.canvas.Clear()

    # =========== Clock Elements =============
    # ========================================

    """ Hour and minute """
    @Animator.KeyFrame.add(frames.PER_SECOND * 0.1)
    def clock(self, count):
        if self.active_plane_display == True:
            self._last_time = None
            return
        CLOCK_FONT = fonts.large_bold
        CLOCK_POSITION = (1, 12)
        CLOCK_COLOR = colors.WARM_WHITE

        now = datetime.datetime.now()
        if CLOCK_24HR == False:
            current_time = now.strftime("%I:%M")
            current_time = current_time[0].replace("0", " ", 1) + current_time[1:] # replace leading zero
        else:
            current_time = now.strftime("%H:%M")

        # Only draw if time needs updating
        if self._last_time != current_time:
            # Undraw last time if different from current
            if self._last_time is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    CLOCK_FONT,
                    CLOCK_POSITION[0],
                    CLOCK_POSITION[1],
                    colors.BLACK,
                    self._last_time,
                )

            self._last_time = current_time

            # Draw Time
            _ = graphics.DrawText(
                self.canvas,
                CLOCK_FONT,
                CLOCK_POSITION[0],
                CLOCK_POSITION[1],
                CLOCK_COLOR,
                current_time,
            )
    
    """ Seconds """
    @Animator.KeyFrame.add(frames.PER_SECOND * 0.1)
    def second(self, count):
        if self.active_plane_display == True:
            self._last_seconds = None
            return
        SECONDS_FONT = fonts.smallest
        SECONDS_POSITION = (41, 12)
        SECONDS_COLOR = colors.WARM_WHITE

        now = datetime.datetime.now()
        current_timesec = now.strftime("%S")

        # Only draw if seconds needs to be updated
        if self._last_seconds != current_timesec:
            # Undraw last seconds if different from current
            if self._last_seconds is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    SECONDS_FONT,
                    SECONDS_POSITION[0],
                    SECONDS_POSITION[1],
                    colors.BLACK,
                    self._last_seconds,
                )

            self._last_seconds = current_timesec

            # Draw seconds
            _ = graphics.DrawText(
                self.canvas,
                SECONDS_FONT,
                SECONDS_POSITION[0],
                SECONDS_POSITION[1],
                SECONDS_COLOR,
                current_timesec,
            )

    """ AM/PM Indicator """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def ampm(self, count):
        if self.active_plane_display == True or CLOCK_24HR == True:
            self._last_ampm = None
            return
        AMPM_COLOR = colors.ORANGE_DARK
        AMPM_FONT = fonts.smallest
        AMPM_POSITION = (41, 6)
        now = datetime.datetime.now()
        current_ampm = now.strftime("%p")

        # Only draw if time needs to be updated
        if self._last_ampm != current_ampm:
            # Undraw last if different from current
            if self._last_ampm is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    AMPM_FONT,
                    AMPM_POSITION[0],
                    AMPM_POSITION[1],
                    colors.BLACK,
                    self._last_ampm,
                )

            self._last_ampm = current_ampm

            # Draw
            _ = graphics.DrawText(
                self.canvas,
                AMPM_FONT,
                AMPM_POSITION[0],
                AMPM_POSITION[1],
                AMPM_COLOR,
                current_ampm,
            )
    
    """ Day of the week """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def day(self, count):
        if self.active_plane_display == True:
            self._last_day = None
            return
        DAY_COLOR = colors.PINK_DARK
        DAY_FONT = fonts.smallest
        DAY_POSITION = (51, 6)
        now = datetime.datetime.now()
        current_day = now.strftime("%a").upper()

        # Only draw if the indicator needs to be updated
        if self._last_day != current_day:
            # Undraw last day if different from current
            if self._last_day is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    DAY_FONT,
                    DAY_POSITION[0],
                    DAY_POSITION[1],
                    colors.BLACK,
                    self._last_day,
                )

            self._last_day = current_day

            # Draw day
            _ = graphics.DrawText(
                self.canvas,
                DAY_FONT,
                DAY_POSITION[0],
                DAY_POSITION[1],
                DAY_COLOR,
                current_day,
            )

    """ Date """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def date(self, count):
        if self.active_plane_display == True:
            self._last_date = None
            return
        DATE_COLOR = colors.PURPLE
        DATE_FONT = fonts.smallest
        DATE_POSITION = (55, 12)
        now = datetime.datetime.now()
        current_date = now.strftime("%d")

        # Only draw if date needs to be updated
        if self._last_date != current_date:
            # Undraw last date if different from current
            if self._last_date is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    DATE_FONT,
                    DATE_POSITION[0],
                    DATE_POSITION[1],
                    colors.BLACK,
                    self._last_date,
                )

            self._last_date = current_date

            # Draw date
            _ = graphics.DrawText(
                self.canvas,
                DATE_FONT,
                DATE_POSITION[0],
                DATE_POSITION[1],
                DATE_COLOR,
                current_date,
            )
    
    # ========= Idle Stats Elements ==========
    # ========================================
    """ Static text """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def idle_header(self, count):
        if self.active_plane_display == True: return
        HEADER_TEXT_FONT = fonts.smallest
        FLYBY_HEADING_COLOR = colors.BLUE_DARK
        TRACK_HEADING_COLOR = colors.GREEN_DARK
        RANGE_HEADING_COLOR = colors.YELLOW_DARK
        IDLE_TEXT_Y = 25
        _ = graphics.DrawText(
            self.canvas,
            HEADER_TEXT_FONT,
            1,
            IDLE_TEXT_Y,
            FLYBY_HEADING_COLOR,
            "FLYBY",
        )
        _ = graphics.DrawText(
            self.canvas,
            HEADER_TEXT_FONT,
            24,
            IDLE_TEXT_Y,
            TRACK_HEADING_COLOR,
            "TRKG",
        )
        _ = graphics.DrawText(
            self.canvas,
            HEADER_TEXT_FONT,
            45,
            IDLE_TEXT_Y,
            RANGE_HEADING_COLOR,
            "RNGE",
        )
    
    """ Our idle stats readout """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def stats_readout(self, count):
        if self.active_plane_display == True:
            self._last_flybys = None
            self._last_track = None
            self._last_range = None
            return
        STATS_TEXT_FONT = fonts.extrasmall
        FLYBY_TEXT_COLOR = colors.BLUE
        TRACK_TEXT_COLOR = colors.GREEN
        RANGE_TEXT_COLOR = colors.YELLOW
        READOUT_TEXT_Y = 31
        FLYBY_X_POS = 1
        TRACK_X_POS = 24
        RANGE_X_POS = 45
        try:
            flybys_now = idle_data['Flybys']
            tracking_now = idle_data['Track']
            range_now = idle_data['Range']
        except: return
        # Undraw sections
        if self._last_flybys != flybys_now:
            if self._last_flybys is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    STATS_TEXT_FONT,
                    FLYBY_X_POS,
                    READOUT_TEXT_Y,
                    colors.BLACK,
                    self._last_flybys,
                )
        if self._last_track != tracking_now:
            if self._last_track is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    STATS_TEXT_FONT,
                    TRACK_X_POS,
                    READOUT_TEXT_Y,
                    colors.BLACK,
                    self._last_track,
                )
        if self._last_range != range_now:
            if self._last_range is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    STATS_TEXT_FONT,
                    RANGE_X_POS,
                    READOUT_TEXT_Y,
                    colors.BLACK,
                    self._last_range,
                )

        # store our current data for readout in the future
        self._last_flybys = flybys_now
        self._last_track = tracking_now
        self._last_range = range_now

        # Update the values on the display
        _ = graphics.DrawText(
            self.canvas,
            STATS_TEXT_FONT,
            FLYBY_X_POS,
            READOUT_TEXT_Y,
            FLYBY_TEXT_COLOR,
            flybys_now,
        )
        _ = graphics.DrawText(
            self.canvas,
            STATS_TEXT_FONT,
            TRACK_X_POS,
            READOUT_TEXT_Y,
            TRACK_TEXT_COLOR,
            tracking_now,
        )
        _ = graphics.DrawText(
            self.canvas,
            STATS_TEXT_FONT,
            RANGE_X_POS,
            READOUT_TEXT_Y,
            RANGE_TEXT_COLOR,
            range_now,
        )

    # ======== Active Plane Readout ==========
    # ========================================
    """ Header information: Callsign, Distance, Country """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def top_header(self, count):
        if self.active_plane_display == False:
            self._last_callsign = None
            self._last_distance = None
            self._last_country = None
            return
        TOP_HEADER_FONT = fonts.smallest
        CALLSIGN_COLOR = colors.WHITE
        DISTANCE_COLOR = colors.WARM_WHITE
        COUNTRY_COLOR = colors.GREY
        BASELINE_Y = 6
        CALLSIGN_X_POS = 1
        DISTANCE_X_POS = 34
        COUNTRY_X_POS = 56
        try:
            callsign_now = active_data['Callsign']
            distance_now = active_data['Distance']
            country_now = active_data['Country']
        except: return
        # Undraw sections
        if self._last_callsign != callsign_now:
            if self._last_callsign is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    TOP_HEADER_FONT,
                    CALLSIGN_X_POS,
                    BASELINE_Y,
                    colors.BLACK,
                    self._last_callsign
                )
        if self._last_distance != distance_now:
            if self._last_distance is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    TOP_HEADER_FONT,
                    DISTANCE_X_POS,
                    BASELINE_Y,
                    colors.BLACK,
                    self._last_distance
                )
        if self._last_country != country_now:
            if self._last_country is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    TOP_HEADER_FONT,
                    COUNTRY_X_POS,
                    BASELINE_Y,
                    colors.BLACK,
                    self._last_country
                )
        # store our current data for readout in the future
        self._last_callsign = callsign_now
        self._last_distance = distance_now
        self._last_country = country_now

        # Update the values on the display
        _ = graphics.DrawText(
            self.canvas,
            TOP_HEADER_FONT,
            CALLSIGN_X_POS,
            BASELINE_Y,
            CALLSIGN_COLOR,
            callsign_now
        )
        _ = graphics.DrawText(
            self.canvas,
            TOP_HEADER_FONT,
            DISTANCE_X_POS,
            BASELINE_Y,
            DISTANCE_COLOR,
            distance_now
        )
        _ = graphics.DrawText(
            self.canvas,
            TOP_HEADER_FONT,
            COUNTRY_X_POS,
            BASELINE_Y,
            COUNTRY_COLOR,
            country_now
        )

    """ Our journey indicator (origin and destination) """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def journey(self, count):
        if self.active_plane_display == False:
            self._last_origin = None
            self._last_destination = None
            return
        def journey_arrow(canvas, x:int, y:int, width:int, height:int, color):
            ARROW_POINT_POSITION = (x, y)
            ARROW_WIDTH = width
            ARROW_HEIGHT = height
            ARROW_COLOR = color

            # Black area before arrow
            self.draw_square(
                ARROW_POINT_POSITION[0] - ARROW_WIDTH,
                ARROW_POINT_POSITION[1] - (ARROW_HEIGHT // 2),
                ARROW_POINT_POSITION[0],
                ARROW_POINT_POSITION[1] + (ARROW_HEIGHT // 2),
                colors.BLACK,
            )

            # Starting positions for filled in arrow
            x = ARROW_POINT_POSITION[0] - ARROW_WIDTH
            y1 = ARROW_POINT_POSITION[1] - (ARROW_HEIGHT // 2)
            y2 = ARROW_POINT_POSITION[1] + (ARROW_HEIGHT // 2)

            # Tip of arrow
            canvas.SetPixel(
                ARROW_POINT_POSITION[0],
                ARROW_POINT_POSITION[1],
                ARROW_COLOR.red,
                ARROW_COLOR.green,
                ARROW_COLOR.blue,
            )

            # Draw using columns
            for col in range(0, ARROW_WIDTH):
                graphics.DrawLine(
                    canvas,
                    x,
                    y1,
                    x,
                    y2,
                    ARROW_COLOR,
                )

                # Calculate next column's data
                x += 1
                y1 += 1
                y2 -= 1

        JOURNEY_Y_BASELINE = 18
        ORIGIN_X_POS = 3
        DESTINATION_X_POS = 37
        JOURNEY_COLOR = colors.ORANGE
        try:
            origin_now = active_data['Origin']
            destination_now = active_data['Destination']
        except: return
        # Undraw method
        if self._last_origin != origin_now or self._last_destination != destination_now:
            if self._last_origin is not None or self._last_destination is not None:
                self.draw_square(
                    0,
                    JOURNEY_Y_BASELINE,
                    64,
                    JOURNEY_Y_BASELINE - 10,
                    colors.BLACK
                )

        # store our current data for readout in the future
        self._last_origin = origin_now
        self._last_destination = destination_now

        # Draw our arrow
        journey_arrow(self.canvas, 33, 13, 4, 8, JOURNEY_COLOR)
        
        # Draw origin; adjust font for all anticipated string lengths
        if len(origin_now) <= 3:
            _ = graphics.DrawText(
                self.canvas,
                fonts.large_bold,
                ORIGIN_X_POS,
                JOURNEY_Y_BASELINE,
                JOURNEY_COLOR,
                origin_now
            )
        elif len(origin_now) == 4:
            _ = graphics.DrawText(
                self.canvas,
                fonts.regularplus,
                ORIGIN_X_POS,
                JOURNEY_Y_BASELINE,
                JOURNEY_COLOR,
                origin_now
            )
        elif len(origin_now) > 4:
            _ = graphics.DrawText(
                self.canvas,
                fonts.extrasmall,
                ORIGIN_X_POS,
                JOURNEY_Y_BASELINE,
                JOURNEY_COLOR,
                origin_now
            )

        # Draw destination; do the same approach as above
        if len(destination_now) <= 3:
            _ = graphics.DrawText(
                self.canvas,
                fonts.large_bold,
                DESTINATION_X_POS,
                JOURNEY_Y_BASELINE,
                JOURNEY_COLOR,
                destination_now
            )
        elif len(destination_now) == 4:
            _ = graphics.DrawText(
                self.canvas,
                fonts.regularplus,
                DESTINATION_X_POS,
                JOURNEY_Y_BASELINE,
                JOURNEY_COLOR,
                destination_now
            )
        elif len(destination_now) > 4:
            _ = graphics.DrawText(
                self.canvas,
                fonts.extrasmall,
                DESTINATION_X_POS,
                JOURNEY_Y_BASELINE,
                JOURNEY_COLOR,
                destination_now
            )

    """ Static text """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def active_header(self, count):
        if self.active_plane_display == False: return
        HEADER_TEXT_FONT = fonts.extrasmall
        ALTITUDE_HEADING_COLOR = colors.BLUE_DARK
        SPEED_HEADING_COLOR = colors.GREEN_DARK
        TIME_HEADING_COLOR = colors.YELLOW_DARK
        ACTIVE_TEXT_Y = 25
        _ = graphics.DrawText(
            self.canvas,
            HEADER_TEXT_FONT,
            1,
            ACTIVE_TEXT_Y,
            ALTITUDE_HEADING_COLOR,
            "ALT"
        )
        _ = graphics.DrawText(
            self.canvas,
            HEADER_TEXT_FONT,
            23,
            ACTIVE_TEXT_Y,
            SPEED_HEADING_COLOR,
            "SPD"
        )
        _ = graphics.DrawText(
            self.canvas,
            HEADER_TEXT_FONT,
            48,
            ACTIVE_TEXT_Y,
            TIME_HEADING_COLOR,
            "TIME"
        )

    """ Our active stats readout """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def active_readout(self, count):
        if self.active_plane_display == False:
            self._last_altitude = None
            self._last_speed = None
            self._last_flighttime = None
            return
        STATS_TEXT_FONT = fonts.smallest
        ALTITUDE_TEXT_COLOR = colors.BLUE
        SPEED_TEXT_COLOR = colors.GREEN
        TIME_TEXT_COLOR = colors.YELLOW
        READOUT_TEXT_Y = 31
        ALTITUDE_X_POS = 1
        SPEED_X_POS = 23
        # TIME_X_POS = 40
        def right_align(string: str) -> int:
            """ special case to align-right the time output """
            length_s = len(string)
            if length_s <= 4: return 50
            elif length_s == 5: return 44
            elif length_s >= 6: return 40
            
        try:
            altitude_now = active_data['Altitude']
            speed_now = active_data['Speed']
            flighttime_now = active_data['FlightTime']
        except: return
        # Undraw sections
        if self._last_altitude != altitude_now:
            if self._last_altitude is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    STATS_TEXT_FONT,
                    ALTITUDE_X_POS,
                    READOUT_TEXT_Y,
                    colors.BLACK,
                    self._last_altitude
                )
        if self._last_speed != speed_now:
            if self._last_speed is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    STATS_TEXT_FONT,
                    SPEED_X_POS,
                    READOUT_TEXT_Y,
                    colors.BLACK,
                    self._last_speed
                )
        if self._last_flighttime != flighttime_now:
            if self._last_flighttime is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    STATS_TEXT_FONT,
                    right_align(self._last_flighttime),
                    READOUT_TEXT_Y,
                    colors.BLACK,
                    self._last_flighttime
                )

        # store our current data for readout in the future
        self._last_altitude = altitude_now
        self._last_speed = speed_now
        self._last_flighttime = flighttime_now

        _ = graphics.DrawText(
            self.canvas,
            STATS_TEXT_FONT,
            ALTITUDE_X_POS,
            READOUT_TEXT_Y,
            ALTITUDE_TEXT_COLOR,
            altitude_now
        )
        _ = graphics.DrawText(
            self.canvas,
            STATS_TEXT_FONT,
            SPEED_X_POS,
            READOUT_TEXT_Y,
            SPEED_TEXT_COLOR,
            speed_now
        )
        _ = graphics.DrawText(
            self.canvas,
            STATS_TEXT_FONT,
            right_align(flighttime_now),
            READOUT_TEXT_Y,
            TIME_TEXT_COLOR,
            flighttime_now
        )

    """ An indicator of how many planes are in the area """
    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def plane_count_indicator(self, count):
        if self.active_plane_display == False:
            self._last_activeplanes = None
            return
        
        def plane_count_indicators(canvas, x_start:int, y_start:int, color, count:int):
            """ draw a stack of pixels to indicate the amount of planes in the area """
            if count > 6: count = 6 # limit to 6
            indicator_color = color
            for i in range(count):
                canvas.SetPixel(
                    x_start,
                    y_start - (i * 2),
                    indicator_color.red,
                    indicator_color.green,
                    indicator_color.blue
                )
        
        INDICATORS_X = 63
        INDICATORS_Y = 17
        plane_count_now = len(relevant_planes)

        # Undraw
        if self._last_activeplanes != plane_count_now:
            if self._last_activeplanes is not None:
                plane_count_indicators(
                    self.canvas,
                    INDICATORS_X,
                    INDICATORS_Y,
                    colors.BLACK,
                    self._last_activeplanes
                    )
        self._last_activeplanes = plane_count_now
        plane_count_indicators(
            self.canvas,
            INDICATORS_X,
            INDICATORS_Y,
            colors.RED,
            self._last_activeplanes
            )

    @Animator.KeyFrame.add(1)
    def sync(self, count):
        # Redraw screen every frame
        _ = self.matrix.SwapOnVSync(self.canvas)

    def run_screen(self):
        try:
            # Start loop
            self.play()

        except (SystemExit, KeyboardInterrupt, ImportError):
            return

# =========== Initialization II ============
# ==========================================

matching_processes = match_commandline(Path(__file__).name, 'python')
if len(matching_processes) > 1: # when we scan for all processes, it will include this process as well
    print("\nERROR: FlightGazer is already running! Only one instance can be running.")
    print("Matching processes:")
    for elem in matching_processes:
        process_ID = elem['pid']
        process_name = elem['name']
        process_started =  time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(elem['create_time']))
        if process_ID != this_process.pid:
            print(f"PID {process_ID} -- [ {process_name} ] started: {process_started}")
    print("")
    time.sleep(1)
    exit(1)
else:
    del matching_processes

configuration_check()
flyby_stats() # initialize first

# define our scheduled tasks
schedule.every().day.at("00:00").do(reset_unique_tracks)
schedule.every().day.at("23:59").do(flyby_stats) # get us the day's total count before reset
schedule.every().hour.at(":00").do(flyby_stats)
if rlat is not None or rlon is not None:
    schedule.every().hour.do(read_1090_config) # in case we have GPS attached and are updating location

dump1090_check()
read_1090_config()

def main() -> None:
    """ Enters the main loop. """
    # register our loop breaker
    if INTERACTIVE == False and FORGOT_TO_SET_INTERACTIVE == False:
        signal.signal(signal.SIGTERM, sigterm_handler)
    if INTERACTIVE == True or FORGOT_TO_SET_INTERACTIVE == True:
        signal.signal(signal.SIGINT, sigterm_handler)
        
    periodic_stuff = threading.Thread(target=schedule_thread, name='Scheduling-Thread', daemon=True)
    periodic_stuff.start()
    main_stuff = threading.Thread(target=main_loop_generator, name='Main-Data-Loop', daemon=True)
    airplane_watcher = threading.Thread(target=AirplaneParser, name='Airplane-Parser', daemon=True)
    api_getter = threading.Thread(target=APIFetcher, name='API-Fetch-Thread', daemon=True)
    display_sender = threading.Thread(target=DisplayFeeder, name='Info-Parser', daemon=True)

    if DISPLAY_VALID == True and NODISPLAY == False:
        print("\nInitializing display...")
        if 'RGBMatrixEmulator' in sys.modules:
            print("We are using \'RGBMatrixEmulator\'")
        else:
            print("We are using \'rgbmatrix\'")
        display = Display()
        display_stuff = threading.Thread(target=display.run_screen, name='Display-Driver', daemon=True)
        display_stuff.start()

    if INTERACTIVE == True:
        print("\nInteractive mode enabled. Pausing here for 15 seconds\n\
so you can read the above output before we enter the main loop.\n")
        interactive_wait_time = 15
        if random.randint(0,1) == 1 and (DISPLAY_VALID == True and EMULATE == False): # randomly show this tip
            interactive_wait_time -= 5
            time.sleep(5)
            print("Protip: If you're not using a physical RBG-Matrix display,\n\
        use RGBMatrixEmulator to see the display on a webpage instead!")
            if 'RGBMatrixEmulator' not in sys.modules:
                print("        It doesn't seem to be installed, so use \'pip install RGBMatrixEmulator\' to get it.")
            
        time.sleep(interactive_wait_time)
        del interactive_wait_time
    
    if INTERACTIVE == False and FORGOT_TO_SET_INTERACTIVE == True:
        print("\nNotice: It seems that this script was run directly instead of through the initalization script.\n\
        Normally, outputs shown here are not usually seen. If you want to see data, use Ctrl+C to quit\n\
        and use the interactive flag (-i) instead.")

    main_stuff.start()
    airplane_watcher.start()
    api_getter.start()
    display_sender.start()
    print("\n========== Main loop started! ===========")
    print("=========================================\n")

    try:
        while True: #keep-alive
            time.sleep(1)
    except ImportError: # catch the display driver (if loaded) exiting and relay it
        sigterm_handler(signal.SIGTERM,"")

# finally
if __name__ == '__main__': main()