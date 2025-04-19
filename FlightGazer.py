#      _/_/_/_/ _/_/    _/            _/        _/       _/_/_/                                    
#     _/         _/         _/_/_/   _/_/_/  _/_/_/_/ _/         _/_/_/ _/_/_/_/   _/_/   _/  _/_/
#    _/_/_/     _/    _/   _/    _/ _/    _/  _/     _/  _/_/ _/    _/     _/   _/_/_/_/ _/_/     
#   _/         _/    _/   _/    _/ _/    _/  _/     _/    _/ _/    _/   _/     _/       _/        
#  _/         _/_/    _/   _/_/_/ _/    _/    _/_/   _/_/_/   _/_/_/ _/_/_/_/   _/_/_/ _/          
#                             _/                               by: WeegeeNumbuh1      
#                        _/_/
                                     
""" 
A flight-tracking program that renders live ADS-B info of nearby aircraft to an RGB-Matrix display.
Heavily inspired by https://github.com/ColinWaddell/its-a-plane-python.
Uses the FlightAware API for info outside what ADS-B can provide.
"""
"""
    Copyright (C) 2025, WeegeeNumbuh1.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
# =============== Imports ==================
# ==========================================
import time
START_TIME: float = time.monotonic()
import datetime
STARTED_DATE: datetime = datetime.datetime.now()
VERSION: str = 'v.4.1.0 --- 2025-04-18'
import os
os.environ["PYTHONUNBUFFERED"] = "1"
import argparse
import sys
import math
from pathlib import Path
import urllib.parse
import json
import signal
import threading
import asyncio
from collections import deque
from string import Formatter
import random
from getpass import getuser
import socket
import logging

if __name__ != '__main__':
    print("FlightGazer cannot be imported as a module.")
    sys.exit(1)

# external imports
import requests
from pydispatch import dispatcher # pip install pydispatcher *not* pip install pydispatch
import schedule
import psutil
from suntime import Sun, SunTimeException
try:
    # faster json deserialization for the dump1090 processing loop
    # Fun stats from testing:
    # - orjson is 2-3x faster than the built-in json module
    # - orjson is 1.05-1.2x faster than msgspec (even after reusing a decoder, as suggested in the msgspec docs)
    import orjson
    ORJSON_IMPORTED = True
except (ModuleNotFoundError, ImportError):
    ORJSON_IMPORTED = False # we can always fall back on the standard json library
# utilities
import utilities.flags as flags
import utilities.registrations as registrations
from utilities.animator import Animator
from setup import frames

argflags = argparse.ArgumentParser(
    description="FlightGazer, a program to show dump1090 info to an RGB-Matrix display.\n\
    Copyright (C) 2025, WeegeeNumbuh1.\n\
    This program comes with ABSOLUTELY NO WARRANTY; for details see the GNU GPL v3.",
    epilog="Protip: Ensure your location is set in your dump1090 configuration!\n\
Report bugs to WeegeeNumbuh1: <https://github.com/WeegeeNumbuh1/FlightGazer>"
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
                      help="Disable filtering and show all aircraft detected by dump1090.\n\
                      Disables API fetching and Display remains as a clock.\n\
                      Implies Interactive mode."
                      )
argflags.add_argument('-v', '--verbose',
                      action='store_true',
                      help="Log/display more detailed messages.\n\
                      This flag is useful for debugging.")
args = argflags.parse_args()
if args.interactive:
    INTERACTIVE: bool = True
else:
    INTERACTIVE = False
if args.emulate:
    EMULATE_DISPLAY: bool = True
else:
    EMULATE_DISPLAY = False
if args.nodisplay:
    NODISPLAY_MODE: bool = True
    INTERACTIVE = True
else:
    NODISPLAY_MODE = False
if args.nofilter:
    NOFILTER_MODE: bool = True
    INTERACTIVE = True
else:
    NOFILTER_MODE = False
if args.verbose:
    VERBOSE_MODE: bool = True
else:
    VERBOSE_MODE = False

FORGOT_TO_SET_INTERACTIVE: bool = False
if os.environ.get('TMUX') is not None or 'tmux' in os.environ.get('TERM', ''):
    INSIDE_TMUX: bool = True
else:
    INSIDE_TMUX = False

# =========== Initialization I =============
# ==========================================

# setup logging
main_logger = logging.getLogger("FlightGazer")
CURRENT_DIR = Path(__file__).resolve().parent
CURRENT_USER = getuser()
LOGFILE = Path(f"{CURRENT_DIR}/FlightGazer-log.log")
try: # should basically work all the time since we're running as root, but this costs nothing
    LOGFILE.touch(mode=0o777, exist_ok=True)
    with open(LOGFILE, 'a') as f:
        f.write("\n") # append a newline at the start of logging
    del f
except PermissionError:
    import tempfile
    workingtempdir = tempfile.gettempdir()
    if os.name == 'posix':
        LOGFILE = Path(f"{workingtempdir}/FlightGazer-log.log")
        LOGFILE.touch(mode=0o777, exist_ok=True)
        with open(LOGFILE, 'a') as f:
            f.write("\n")
        del f
    if os.name == 'nt':
        LOGFILE = Path(f"{workingtempdir}/FlightGazer-log.log")
        LOGFILE.touch(mode=0o777, exist_ok=True)
        with open(LOGFILE, 'a') as f:
            f.write("\n")
        del f

logging_format = logging.Formatter(
    fmt='%(asctime)s.%(msecs)03d - %(threadName)s | %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    )

# set root logger to write out to file but not stdout
logging.basicConfig(
    filename=LOGFILE,
    format='%(asctime)s.%(msecs)03d - %(name)s %(threadName)s | %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8',
    level=logging.DEBUG if VERBOSE_MODE else logging.INFO,
)

# add a stdout stream for the logger that we can disable if we run interactively
# NB: in `main_logger.handlers` this handler will be in index 0 (the default one we set above does not add a handler),
# so to stop the stdout stream, use main_logger.removeHandler()
stdout_stream = logging.StreamHandler(sys.stdout)
stdout_stream.setLevel(logging.NOTSET)
stdout_stream.setFormatter(logging_format)
main_logger.addHandler(stdout_stream)

# When logging level is set to DEBUG, the requests library will spam the log for each time dump1090 is polled.
# While verbosity is nice, this is excessive, so we bump up the logging level
logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

main_logger.info("==============================================================")
main_logger.info("===                 Welcome to FlightGazer!                ===")
main_logger.info("==============================================================")
main_logger.info(f"FlightGazer Version: {VERSION}")
main_logger.info(f"Script started: {STARTED_DATE.replace(microsecond=0)}")
main_logger.info(f"We are running in \'{CURRENT_DIR}\'")
main_logger.info(f"Using: \'{sys.executable}\' as \'{CURRENT_USER}\' with PID: {os.getpid()}")
if LOGFILE != Path(f"{CURRENT_DIR}/FlightGazer-log.log"):
    main_logger.error(f"***** Could not write log file! Using temp directory: {LOGFILE} *****")
main_logger.info(f"Running inside tmux?: {INSIDE_TMUX}")

# Main "constants"
FLYBY_STATS_FILE = Path(f"{CURRENT_DIR}/flybys.csv")
CONFIG_FILE = Path(f"{CURRENT_DIR}/config.yaml")
API_URL: str = "https://aeroapi.flightaware.com/aeroapi/"
USER_AGENT: dict = {'User-Agent': "Wget/1.25.0"}
""" Use Wget user-agent for our requests """
LOOP_INTERVAL: float = 2
""" in seconds. Affects how often we poll `dump1090`'s json (which itself atomically updates every second).
Affects how often other processing threads handle data as they are triggered on every update. """
RGB_COLS: int = 64
RGB_ROWS: int = 32
API_COST_PER_CALL: float = 0.005
""" How much it costs to do a single API call (may change in the future).
Current as of `VERSION` """
if VERBOSE_MODE:
    main_logger.debug("Verbose mode enabled.")
    # main_logger.debug("Connected loggers:")
    # for key in logging.Logger.manager.loggerDict:
    #     main_logger.debug(f"{key}")

# load in all the display-related modules
DISPLAY_IS_VALID: bool = True
if not NODISPLAY_MODE:
    try:
        if not EMULATE_DISPLAY:
            try:
                from rgbmatrix import graphics
                from rgbmatrix import RGBMatrix, RGBMatrixOptions
            except (ModuleNotFoundError, ImportError):
                main_logger.warning("rgbmatrix software framework not found. Switching to display emulation mode.")
                EMULATE_DISPLAY = True

        if EMULATE_DISPLAY:
            try:
                # monkey patch this so it loads the config file from our running directory
                os.environ['RGBME_SUPPRESS_ADAPTER_LOAD_ERRORS'] = "True"
                from RGBMatrixEmulator.emulation.options import RGBMatrixEmulatorConfig
                RGBMatrixEmulatorConfig.CONFIG_PATH = Path(f"{CURRENT_DIR}/emulator_config.json")

                from RGBMatrixEmulator import graphics
                from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
            except (ModuleNotFoundError, ImportError):
                DISPLAY_IS_VALID = False
                main_logger.error("Display module \'RGBMatrixEmulator\' not found or failed to load. There will be no display output!")
                main_logger.warning(">>> Please check the working environment, reboot the system, and do a reinstallation if necessary.")
                main_logger.warning("    If this error continues to occur, submit a bug report to the developer.")
                main_logger.warning(">>> This script will still function as a basic flight parser and stat generator,")
                main_logger.warning("    if the environment allows.")
                main_logger.warning(">>> If you're sure you don't want to use any display output,")
                main_logger.warning("    use the \'-d\' flag to suppress this warning.")
                time.sleep(2)
        
        # these modules depend on the above, so they should load successfully at this point,
        # but if they break somehow, we can still catch it
        from setup import colors, fonts

    except Exception as e:
        DISPLAY_IS_VALID = False
        main_logger.error("Display modules failed to load. There will be no display output!")
        main_logger.error(f"Error details regarding \'{e}\':", exc_info=True)
        main_logger.warning(">>> Please check the working environment, reboot the system, and do a reinstallation if necessary.")
        main_logger.warning("    If this error continues to occur, submit a bug report to the developer.")
        main_logger.warning(">>> This script will still function as a basic flight parser and stat generator")
        main_logger.warning("    if the environment allows.")
        main_logger.warning(">>> If you're sure you don't want to use any display output,")
        main_logger.warning("    use the \'-d\' flag to suppress this warning.")
        time.sleep(2)
else:
    DISPLAY_IS_VALID = False
    main_logger.info("Display output disabled. Running in console-only mode.")

if not VERBOSE_MODE: sys.tracebacklimit = 0 # supress tracebacks; it should be handled from here on out

# If we invoked this script by terminal and we forgot to set any flags, set this flag.
# This affects how to handle our exit signals (previously)
if not INTERACTIVE:
    if sys.__stdin__.isatty(): FORGOT_TO_SET_INTERACTIVE = True

# make additional use for psutil
this_process = psutil.Process()
this_process_cpu = this_process.cpu_percent(interval=None)
CORE_COUNT = os.cpu_count()
if CORE_COUNT is None: CORE_COUNT = 1

# =========== Settings Load-in =============
# ==========================================

# Define our settings and initialize to defaults
FLYBY_STATS_ENABLED: bool = False
HEIGHT_LIMIT: int|float = 15000
RANGE: int|float = 2
API_KEY: str|None = ""
API_DAILY_LIMIT: int|None = None
CLOCK_24HR: bool = True
CUSTOM_DUMP1090_LOCATION: str = ""
CUSTOM_DUMP978_LOCATION: str = ""
BRIGHTNESS: int = 100
GPIO_SLOWDOWN: int = 2
HAT_PWM_ENABLED: bool = False
LED_PWM_BITS: int = 8
UNITS: int = 0
FLYBY_STALENESS: int = 60
ENHANCED_READOUT: bool = False
ENABLE_TWO_BRIGHTNESS: bool = True
BRIGHTNESS_2: int = 50
BRIGHTNESS_SWITCH_TIME: dict = {"Sunrise":"06:00","Sunset":"18:00"}
USE_SUNRISE_SUNSET: bool = True
ACTIVE_PLANE_DISPLAY_BRIGHTNESS: int|None = None
LOCATION_TIMEOUT: int = 60
ENHANCED_READOUT_AS_FALLBACK: bool = False
FOLLOW_THIS_AIRCRAFT: str = ""
DISPLAY_SWITCH_PROGRESS_BAR: bool = True
CLOCK_CENTER_ROW: dict = {"ROW1":None,"ROW2":None}
ALTERNATIVE_FONT: bool = False
API_COST_LIMIT: float|None = None
JOURNEY_PLUS: bool = False
FASTER_REFRESH: bool = False
PREFER_LOCAL: bool = True
WRITE_STATE: bool = True # new setting!

# Programmer's notes for settings that are dicts:
# Don't change key names or extend the dict. You're stuck with them once baked into this script.
# Why? The settings migrator can't handle migrating dicts that have different keys.
# ex: SETTING = {'key1':val1, 'key2':val2} (user's settings)
#     SETTING = {'key1':val10, 'key2':val20, 'key3':val3} (some hypothetical extension for SETTING in new config)
#     * settings migration *
#     SETTING = {'key1':val1, 'key2':val2} (migrated settings)

# Create our settings as a dict
# NB: if we don't want to load certain settings,
#     we can simply remove elements from this dictionary
#     but be cautious of leaving out keys that are used elsewhere
default_settings: dict = {
    "FLYBY_STATS_ENABLED": FLYBY_STATS_ENABLED,
    "HEIGHT_LIMIT": HEIGHT_LIMIT,
    "RANGE": RANGE,
    "API_KEY": API_KEY,
    "API_DAILY_LIMIT": API_DAILY_LIMIT,
    "CLOCK_24HR": CLOCK_24HR,
    "CUSTOM_DUMP1090_LOCATION": CUSTOM_DUMP1090_LOCATION,
    "CUSTOM_DUMP978_LOCATION": CUSTOM_DUMP978_LOCATION,
    "BRIGHTNESS": BRIGHTNESS,
    "GPIO_SLOWDOWN": GPIO_SLOWDOWN,
    "HAT_PWM_ENABLED": HAT_PWM_ENABLED,
    "LED_PWM_BITS": LED_PWM_BITS,
    "UNITS": UNITS,
    "FLYBY_STALENESS": FLYBY_STALENESS,
    "ENHANCED_READOUT": ENHANCED_READOUT,
    "ENABLE_TWO_BRIGHTNESS": ENABLE_TWO_BRIGHTNESS,
    "BRIGHTNESS_2": BRIGHTNESS_2,
    "BRIGHTNESS_SWITCH_TIME": BRIGHTNESS_SWITCH_TIME,
    "USE_SUNRISE_SUNSET": USE_SUNRISE_SUNSET,
    "ACTIVE_PLANE_DISPLAY_BRIGHTNESS": ACTIVE_PLANE_DISPLAY_BRIGHTNESS,
    "LOCATION_TIMEOUT": LOCATION_TIMEOUT,
    "ENHANCED_READOUT_AS_FALLBACK": ENHANCED_READOUT_AS_FALLBACK,
    "FOLLOW_THIS_AIRCRAFT": FOLLOW_THIS_AIRCRAFT,
    "DISPLAY_SWITCH_PROGRESS_BAR": DISPLAY_SWITCH_PROGRESS_BAR,
    "CLOCK_CENTER_ROW": CLOCK_CENTER_ROW,
    "ALTERNATIVE_FONT": ALTERNATIVE_FONT,
    "API_COST_LIMIT": API_COST_LIMIT,
    "JOURNEY_PLUS": JOURNEY_PLUS,
    "FASTER_REFRESH": FASTER_REFRESH,
    "PREFER_LOCAL": PREFER_LOCAL,
    "WRITE_STATE": WRITE_STATE,
}
""" Dict of default settings """

CONFIG_MISSING: bool = False
main_logger.info("Loading configuration...")
config_version: None|str = None
try:
    from ruamel.yaml import YAML
    yaml = YAML()
except:
    main_logger.warning("Failed to load required module \'ruamel.yaml\'. Configuration file cannot be loaded.")
    main_logger.info(">>> Using default settings.")
    CONFIG_MISSING = True
if not CONFIG_MISSING:
    try:
        config = yaml.load(open(CONFIG_FILE, 'r'))
    except:
        main_logger.warning(f"Cannot find configuration file \'config.yaml\' in \'{CURRENT_DIR}\'")
        main_logger.info(">>> Using default settings.")
        CONFIG_MISSING = True
if not CONFIG_MISSING:
    try:
        config_version = config['CONFIG_VERSION']
    except KeyError:
        main_logger.warning("Warning: Cannot determine configuration version. This may not be a valid FlightGazer config file.")
        main_logger.info(">>> Using default settings.")
        CONFIG_MISSING = True

''' We do the next block to enable backward compatibility for older config versions.
In the future, additional settings could be defined, which older config files
will not have, so we attempt to load what we can and handle cases when the setting value is missing.
This shouldn't be an issue when FlightGazer is updated with the update script, but we still have to import the settings. '''
if not CONFIG_MISSING:
    for setting_key in default_settings:
        try:
            globals()[f"{setting_key}"] = config[setting_key] # match setting key from config file with expected keys
        except:
            # ensure we can always revert to default values 
            globals()[f"{setting_key}"] = default_settings[setting_key]
            main_logger.warning(f"{setting_key} missing, using default value")
    else:
        main_logger.info(f"Loaded settings from configuration file. Version: {config_version}")
        del setting_key
if config: del config

if FASTER_REFRESH:
    LOOP_INTERVAL = 1

# =========== Global Variables =============
# ==========================================

general_stats: dict = {'Tracking':0, 'Range':0}
""" General dump1090 stats (updated per loop).
`general_stats` = {`Tracking`, `Range`} """
receiver_stats: dict = {'Gain':None, 'Noise':None, 'Strong':None}
""" Receiver stats (if available). None values for keys if data is unavailable. 
`receiver_stats` = {`Gain`: float, `Noise`: float (negative), `Strong`: percentage} """

# active plane stuff
relevant_planes: list = []
""" List of planes and associated stats found inside area of interest (refer to `main_loop_generator.dump1090_loop()` for keys) """
focus_plane: str = ""
""" Current plane in focus, selected by `AirplaneParser.plane_selector()`. Defaults to an empty string when no active plane is selected. """
focus_plane_stats: dict = {}
""" Extracted stats for `focus_plane` from `relevant_planes` """
focus_plane_iter: int = 0
""" Variable that increments per loop when `AirplaneParser` is active """
focus_plane_ids_scratch = set()
""" Scratchpad of currently tracked planes (all IDs in `relevant_planes` at current loop).
Elements can be removed if plane count > 1 due to selector algorithm """
focus_plane_ids_discard = set()
""" Scratchpad of previously tracked plane IDs during the duration of `AirplaneParser`'s execution """
plane_latch_times: list = [
    int(30 // LOOP_INTERVAL),
    int(20 // LOOP_INTERVAL),
    int(15 // LOOP_INTERVAL),
]
""" Precomputed table of latch times (loops) for plane selection algorithm. [2 planes, 3 planes, 4+ planes] """
focus_plane_api_results = deque([None] * 100, maxlen=100)
""" Additional API-derived information for `focus_plane` and previously tracked planes from FlightAware API.
Valid keys are {`ID`, `Flight`, `Origin`, `Destination`, `Departure`, `APIAccessed`} """
unique_planes_seen: list = []
""" List of nested dictionaries that tracks unique hex IDs of all plane flybys in a day.
Keys are {`ID`, `Time`} """

# display stuff
idle_data: dict = {'Flybys': "0", 'Track': "0", 'Range': "0"}
""" Formatted dict for our Display driver.
`idle_data` = {`Flybys`, `Track`, `Range`} """
idle_data_2: dict = {'SunriseSunset': "", 'ReceiverStats': ""}
""" Additional formatted dict for our Display driver.
`idle_data_2` = {`SunriseSunset`, `ReceiverStats`} """
active_data: dict = {}
""" Formatted dict for our Display driver.
`active_data` = {
`Callsign`, `Origin`, `Destination`, `FlightTime`,
`Altitude`, `Speed`, `Distance`, `Country`,
`Latitude`, `Longitude`, `Track`, `VertSpeed`, `RSSI`
} or {} """
active_plane_display: bool = False
""" Which scene to put on the display. False = clock/idle, True = active plane """
current_brightness: int = BRIGHTNESS
""" Commanded brightness level for the display; may be changed depending on settings """

# location stuff
rlat: float | None = None
""" Our location latitude """
rlon: float | None = None
""" Our location longitude """
sunset_sunrise: dict = {"Sunrise": None, "Sunset": None}
""" Sunrise and sunset times for our location in datetime format.
Updated every day at midnight via the scheduler. Defaults to None if times cannot be determined. """
CURRENT_IP = ""
""" IP address of device running this script """

# runtime stuff
DUMP1090_IS_AVAILABLE: bool = False
""" If we fail to load dump1090, set to False and continue. Set to True when connected to dump1090.
This is also changed to False when the watchdog kicks in. """
process_time: list = [0.,0.,0.,0.]
""" [dump1090 response, filter data, API response, frame render] ms """
api_hits: list = [0,0,0,0]
""" [successful API returns, failed API returns, no data returned, cache hits] """
flyby_stats_present: bool = False
""" Flag to check if we can write to `FLYBY_STATS_FILE`, initialized to False """
dump1090_failures: int = 0
""" Track amount of times we fail to read dump1090 data. """
dump1090_failures_to_watchdog_trigger: int = 20
""" Number of times that we fail to read dump1090 data before triggering the watchdog. """
watchdog_triggers: int = 0
""" Track amount of times the watchdog is triggered. If this amount exceeds
`watchdog_setpoint`, permanently disable watching dump1090 for this session. """
watchdog_setpoint: int = 3
""" How many times the watchdog is allowed to be triggered before permanently disabling dump1090 tracking """
selection_events: int = 0
""" Track amount of times the plane selector is triggered. (this is just a verbose stat) """
API_daily_limit_reached: bool = False
""" This flag will be set to True if we reach `API_DAILY_LIMIT`.
Currently controls the fallback for ENHANCED_READOUT. """
dump1090_receiver_version: str = ''
""" What version of dump1090 we're connected to as read from the `receiver.json` file. """
is_readsb: bool = False
""" Tweak text output if we're connected to wiedehopf's readsb instead of dump1090 """
dump1090: str = "readsb" if is_readsb else "dump1090"
""" dump1090 or readsb """
ENHANCED_READOUT_INIT: bool = False
""" State of ENHANCED_READOUT after successfully parsing settings file """
CPU_TEMP_SENSOR: str | None = None
""" CPU temperature sensor present on system """
CLOCK_CENTER_ENABLED: bool = False
""" True when CLOCK_CENTER_ROW is not None """
CLOCK_CENTER_ROW_2ROWS: bool = False
""" True when CLOCK_CENTER_ROW is set to use two rows """
api_usage_cost_baseline: float = 0.
""" API usage when we first started FlightGazer, and updated at around midnight. """
estimated_api_cost: float = 0.
""" API usage so far in the day. Resets at midnight. """
API_cost_limit_reached: bool = False
""" Flag to indicate we hit the defined cost limit. """
process_time2: list = [0.,0.,0.,0.]
""" Actual debug info: [time to print last console output, format data, json deserializing, json serializing] ms """
runtime_sizes: list = [0,0,0]
""" Actual debug info: [dump1090 json size, reserved, reserved] bytes """
display_fps: float = 0.
""" FPS of the display animator """
display_failures: int = 0
""" Track how many times the display broke """
USING_FILESYSTEM: bool = False
""" True if we are directly accessing the dump1090 json via the local file system instead of through the network """
USING_FILESYSTEM_978: bool = False
""" True if we are directly accessing dump978 json from the file system """
algorithm_rare_events: int = 0
""" Count of times the rare events section of the selection algorithm is used """

# hashable objects for our cross-thread signaling
DATA_UPDATED: str = "updated-data"
PLANE_SELECTED: str = "plane-in-range"
PLANE_SELECTOR_DONE: str = "there-is-plane-data"
DISPLAY_SWITCH: str = "reset-scene"
END_THREADS: str = "terminate"
KICK_DUMP1090_WATCHDOG: str = "kick-watchdog"

# define our units and multiplication factors (based on aeronautical units)
distance_unit: str = "nmi"
altitude_unit: str = "ft"
speed_unit: str = "kt"
distance_multiplier: float = 1
altitude_multiplier: float = 1
speed_multiplier: float = 1

if UNITS is None\
   or not isinstance(UNITS, int)\
   or UNITS == 0\
   or UNITS < 0\
   or UNITS > 2:
    main_logger.info("Using default aeronautical units (nmi, ft, kt)")
elif UNITS == 1: # metric
    distance_unit = "km"
    altitude_unit = "m"
    speed_unit = "km/h"
    distance_multiplier = 1.852
    altitude_multiplier = 0.3048
    speed_multiplier = 1.85184
    main_logger.info("Using metric units (km, m, km/h)")
elif UNITS == 2: # imperial
    distance_unit = "mi"
    speed_unit = "mph"
    distance_multiplier = 1.150779
    speed_multiplier = 1.150783
    main_logger.info("Using imperial units (mi, ft, mph)")

# =========== Program Setup I ==============
# =============( Utilities )================

def has_key(book, key):
    return (key in book)

def sigterm_handler(signum, frame):
    """ Shutdown worker threads and exit this program. """
    signal.signal(signum, signal.SIG_IGN) # ignore additional signals
    exit_time = datetime.datetime.now()
    end_time = round(time.monotonic() - START_TIME, 3)
    dispatcher.send(message='', signal=END_THREADS, sender=sigterm_handler)
    os.write(sys.stdout.fileno(), str.encode(f"\n- Exit signal commanded at {exit_time}\n"))
    os.write(sys.stdout.fileno(), str.encode(f"  Script ran for {timedelta_clean(end_time)}\n"))
    os.write(sys.stdout.fileno(), str.encode(f"Shutting down... "))
    # write the above message to the log file
    main_logger.info(f"- Exit signal commanded at {exit_time}")
    main_logger.info(f"  Script ran for {timedelta_clean(end_time)}")
    flyby_stats()
    os.write(sys.stdout.fileno(), b"Done.\n")
    main_logger.info("FlightGazer is shutdown.")
    sys.exit(0)

def register_signal_handler(loop, handler, signal, sender) -> None:
    """ Thread communication enabler. """
    def dispatcher_receive(message):
        loop.call_soon_threadsafe(handler, message)
    dispatcher.connect(dispatcher_receive, signal=signal, sender=sender, weak=False)

def schedule_thread() -> None:
    """ Our schedule runner """
    while True:
        schedule.run_pending()
        time.sleep(1)

def cls() -> None:
    """ Clear the console when using a terminal """
    os.system('cls' if os.name=='nt' else 'clear')

def timedelta_clean(timeinput: datetime) -> str:
    """ Cleans up time deltas without the microseconds. """
    delta_time = datetime.timedelta(seconds=timeinput)
    return f"{delta_time}".split(".")[0]

def strfdelta(tdelta, fmt='{D:02}d {H:02}h {M:02}m {S:02}s', inputtype='timedelta') -> str:
    """Convert a datetime.timedelta object or a regular number to a custom-
    formatted string, just like the stftime() method does for datetime.datetime
    objects. Sourced from https://stackoverflow.com/a/42320260

    The fmt argument allows custom formatting to be specified.  Fields can 
    include seconds, minutes, hours, days, and weeks.  Each field is optional.

    Some examples:
    >>> '{D:02}d {H:02}h {M:02}m {S:02}s' --> '05d 08h 04m 02s' (default)
    >>> '{W}w {D}d {H}:{M:02}:{S:02}'     --> '4w 5d 8:04:02'
    >>> '{D:2}d {H:2}:{M:02}:{S:02}'      --> ' 5d  8:04:02'
    >>> '{H}h {S}s'                       --> '72h 800s'

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

def runtime_accumulators_reset() -> None:
    """ Resets the tracked planes set and other daily accumulators.
    Also is responsible to the API cost polling. (this function is scheduled to run at midnight) """
    date_now_str = (datetime.datetime.now() - datetime.timedelta(seconds=10)).strftime('%Y-%m-%d')
    time.sleep(2) # wait for hourly events to complete
    global unique_planes_seen, selection_events, ENHANCED_READOUT
    global api_hits, API_daily_limit_reached, api_usage_cost_baseline, estimated_api_cost, API_cost_limit_reached
    if algorithm_rare_events == 0:
        main_logger.info(f"DAILY STATS for {date_now_str}: {len(unique_planes_seen)} flybys.")
    else:
        main_logger.info(f"DAILY STATS for {date_now_str}: {len(unique_planes_seen)} flybys. {selection_events} selection events \
(of which {algorithm_rare_events} were rare selection events).")
    if sum(api_hits) > 0: # if we used the API at all
        main_logger.info(f"API STATS   for {date_now_str}: {api_hits[0]}/{api_hits[0]+api_hits[1]} successful API calls, of which {api_hits[2]} returned no data. \
Estimated cost: ${estimated_api_cost:.2f}")
    with threading.Lock():
        unique_planes_seen.clear()
        for i in range(len(api_hits)):
            api_hits[i] = 0
        if ENHANCED_READOUT_AS_FALLBACK and API_daily_limit_reached:
            ENHANCED_READOUT = False
            API_daily_limit_reached = False
            main_logger.info("API calls have been reset. Restoring to previous display mode (ENHANCED_READOUT = False).")
        selection_events = 0

    # update current API usage to what's reported on FlightAware's side
    if API_KEY:
        api_calls, api_cost = probe_API()
        api_usage_cost_sofar = api_usage_cost_baseline + estimated_api_cost
        if api_cost is not None:
            main_logger.info(f"Queried API, actual usage is ${api_cost:.2f}, with {api_calls} total calls over the past 30 days.")
            api_usage_cost_baseline = api_cost
            main_logger.debug(f"Difference between calculated (${api_usage_cost_sofar:.3f}) and actual cost: ${abs(api_usage_cost_sofar - api_cost):.3f}")
            if API_COST_LIMIT is not None:
                estimated_api_cost = 0.
                if api_cost < API_COST_LIMIT:
                    main_logger.info(f"${API_COST_LIMIT - api_cost:.2f} of API credit remains before reaching cost limit (${API_COST_LIMIT:.2f}).")
                    if API_cost_limit_reached:
                        main_logger.info(f"There are credits available again, API will be re-enabled.")
                        API_cost_limit_reached = False
                else:
                    main_logger.info(f"API usage currently exceeds the set cost limit (${API_COST_LIMIT:.2f}).")
                    if not API_cost_limit_reached:
                        API_cost_limit_reached = True
        else: # don't reset/adjust the counters
            main_logger.warning("Unable to query API usage, will try again in 24 hours.")
            if API_COST_LIMIT is not None:
                main_logger.info(f">>> Running on the assumption that ${API_COST_LIMIT - api_usage_cost_sofar:.2f} of credit remains.")

    return

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
    else:
        psutil.process_iter.cache_clear() # psutil 6.0+; we don't need the cache
 
    return list_of_processes

def get_ip() -> None:
    ''' Gets us our local IP. Modified from my other project `UNRAID Status Screen`.
    Modifies the global `CURRENT_IP` '''
    global CURRENT_IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1)) # doesn't even need to connect
        IP = s.getsockname()[0]
    except Exception:
        IP = ""
    finally:
        s.close()
    CURRENT_IP = IP

def get_cpu_temp_sensor() -> str | None:
    ''' Determines what CPU temp sensor (if available) is present.
    Modified from my other project, UNRAID Status Screen. '''

    if not hasattr(psutil, "sensors_temperatures"):
        return None
    else:
        # check if there are any temperature sensors on the system
        temps_test = psutil.sensors_temperatures()
        if not temps_test:
            return None
    
    # probe possible temperature names    
    # generic names, then Intel, then AMD
    probe_sensor_names = iter(['cpu_thermal', 'cpu_thermal_zone', 'coretemp', 'k10temp', 'k8temp',])
    # try until we hit our first success
    while True:
        sensor_entry = next(probe_sensor_names, "nothing")
        if sensor_entry == "nothing":
            return None
        try:
            test1 = psutil.sensors_temperatures()[sensor_entry][0].current
            return sensor_entry
        except:
            pass

# =========== Program Setup II =============
# ========( Initialization Tools )==========

def probe1090() -> tuple[str | None, str | None]:
    """ Determines which json exists on the system. Returns `JSON1090_LOCATION` and its base `URL` 
    If `PREFER_LOCAL` is enabled, this function will try to see if it can access dump1090 from the local
    file system and use that if it works first. When this happens, `USING_FILESYSTEM` flag will be set. """
    global USING_FILESYSTEM
    if PREFER_LOCAL and os.name=='posix':
        # file locations sourced from https://raw.githubusercontent.com/wiedehopf/tar1090/master/install.sh
        file_locations = [
            "/run/readsb",
            "/run/dump1090-fa",
            "/run/adsb-feeder-ultrafeeder/readsb", # ultrafeeder/adsb.im setups
            "/run/dump1090",
            "/run/dump1090-mutability", # Pi24 uses this
            "/run/adsbexchange-feed",
            "/run/shm", # AirNav's rbfeeder
            ]
        for i, json_1090 in enumerate(file_locations):
            if Path(f"{json_1090}/aircraft.json").is_file():
                USING_FILESYSTEM = True
                main_logger.info("A local working dump1090 instance was found running on this system.")
                return json_1090 + '/aircraft.json', json_1090
        else:
            main_logger.debug("No local running instance of dump1090 present on the system, falling back to using the network.")

    locations = iter(
        [CUSTOM_DUMP1090_LOCATION,
         "http://localhost/tar1090",
         "http://localhost/skyaware",
         "http://localhost/dump1090-fa",
         "http://localhost:8080",]
         )
    while True:
        json_1090 = next(locations, "nothing")
        if json_1090 == "nothing":
            return None, None
        try:
            test1 = requests.get(json_1090 + '/data/aircraft.json', headers=USER_AGENT, timeout=0.5)
            test1.raise_for_status()
            return json_1090 + '/data/aircraft.json', json_1090
        except:
            pass

def probe978() -> str | None:
    """ Check if dump978 exists and returns its `URL` or None if not found. """
    global USING_FILESYSTEM_978
    if PREFER_LOCAL and os.name=='posix':
        file_locations = [
            "/run/skyaware978",
            "/run/adsb-feeder-ultrafeeder/skyaware978",
            "/run/adsbexchange-978",
        ]
        for i, json_978 in enumerate(file_locations):
            if Path(f"{json_978}/aircraft.json").is_file():
                USING_FILESYSTEM_978 = True
                main_logger.info(f"dump978 detected as well, at \'{json_978}\'")
                return json_978 + '/aircraft.json'
        else:
            main_logger.debug("No local running instance of dump978 present on the system, falling back to using the network.")
        
    locations = iter(
        ["http://localhost:8978",
         CUSTOM_DUMP978_LOCATION]
    )
    while True:
        json_978 = next(locations, "nothing")
        if json_978 == "nothing": break
        try:
            test1 = requests.get(json_978 + '/data/aircraft.json', headers=USER_AGENT, timeout=0.5)
            test1.raise_for_status()
            main_logger.info(f"dump978 detected as well, at \'{json_978}\'")
            return json_978 + '/data/aircraft.json'
        except:
            pass
    return None

def dump1090_check() -> None:
    """ Checks what dump1090 we have available upon startup. If we can't find it, just become a clock. """
    global DUMP1090_JSON, URL, DUMP978_JSON, DUMP1090_IS_AVAILABLE
    main_logger.info("Searching for dump1090...")
    if PREFER_LOCAL and not os.name=='posix':
        main_logger.info(f"PREFER_LOCAL is enabled but this is not a posix system. Falling back to using the network.")
    for wait in range(3):
        tries = 3 - wait
        DUMP1090_JSON, URL = probe1090()
        if DUMP1090_JSON is not None:
            main_logger.info(f"Found dump1090 at \'{URL}\'")
            DUMP1090_IS_AVAILABLE = True
            break
        else:
            main_logger.info(f"Could not find dump1090.json. dump1090 may not be loaded yet. Waiting 10 seconds and trying {tries} more time(s).")
            time.sleep(10)
    else: # try it again one last time
        DUMP1090_JSON, URL = probe1090()

    if DUMP1090_JSON is None:
        DUMP1090_IS_AVAILABLE = False
        if DISPLAY_IS_VALID:
            main_logger.error("dump1090 not found. This will just be a cool-looking clock until this program is restarted.")
        else:
            main_logger.critical("dump1090 not found. Additionally, screen resources are missing!")
    DUMP978_JSON = probe978() # we don't wait for this one as it's usually not present

def read_1090_config() -> None:
    """ Gets us our location (if it's configured) and what ADS-B decoder we're attached to. """
    global rlat, rlon, dump1090_receiver_version, is_readsb
    if not DUMP1090_IS_AVAILABLE: return
    try:
        if USING_FILESYSTEM:
            with open(Path(URL + '/receiver.json'), 'rb') as receiver_file:
                receiver = json.load(receiver_file)
        else:
            receiver_req = requests.get(URL + '/data/receiver.json', headers=USER_AGENT, timeout=5)
            receiver_req.raise_for_status()
            receiver = receiver_req.json()

        with threading.Lock():
            rlat_last = rlat
            rlon_last = rlon
            version_last = dump1090_receiver_version

            # avoid printing this every time we run this function
            if has_key(receiver, 'version') and receiver['version'] != version_last:
                dump1090_receiver_version = receiver['version']
                main_logger.info(f"ADS-B receiver version: \'{dump1090_receiver_version}\'")
                if 'wiedehopf' in dump1090_receiver_version:
                    is_readsb = True
                    main_logger.debug("Connected to readsb!")
            elif not has_key(receiver, 'version'):
                main_logger.warning("Connected to an unknown ADS-B decoder.")

            if has_key(receiver,'lat'): #if location is set
                if receiver['lat'] != rlat_last or receiver['lon'] != rlon_last:
                    rlat = float(receiver['lat'])
                    rlon = float(receiver['lon'])
                    main_logger.info(f"Location updated.")
                    main_logger.debug(f">>> ({rlat}, {rlon})")
            else:
                rlat = rlon = None
                main_logger.warning("Location has not been set! This program will not be able to determine any nearby aircraft or calculate range!")
                main_logger.warning(">>> Please set location in dump1090 to disable this message.")
    except:
        main_logger.error("Cannot load receiver config.")
    return

def probe_API() -> tuple[int | None, float | None]:
    """ Checks if the provided API Key is valid, and if it is, pulls stats from the last 30 days.
    This specific query doesn't use API credits according to the API reference. If the call fails, returns None. """
    if API_KEY is None or not API_KEY: return None, None
    if NOFILTER_MODE or ENHANCED_READOUT: return None, None
    api_calls = 0
    api_cost = 0
    date_now = datetime.datetime.now()
    time_delta_last_month = date_now - datetime.timedelta(days=30)
    date_month_iso = time_delta_last_month.astimezone().replace(microsecond=0).isoformat()
    auth_header = {'x-apikey':API_KEY, 'Accept':"application/json; charset=UTF-8"}
    query_string = (API_URL
                    + "account/usage"
                    + "?start=" + urllib.parse.quote(date_month_iso)
                    )
    try:
        response = requests.get(query_string, headers=auth_header, timeout=10)
        response.raise_for_status()
        if response.status_code == 200:
            response_json = response.json()
            api_calls: int = response_json['total_calls']
            api_cost: float = response_json['total_cost']
            return api_calls, api_cost
        else:
            return None, None
    except KeyError:
        main_logger.warning(f"API returned a response that cannot be parsed.")
        return None, None
    except:
        main_logger.debug(f"API call failed. Returned: {response.status_code}")
        return None, None
    
def configuration_check() -> None:
    """ Configuration checker and runtime adjustments. Actually very important. """
    global RANGE, HEIGHT_LIMIT, FLYBY_STATS_ENABLED, FLYBY_STALENESS, LOCATION_TIMEOUT, FOLLOW_THIS_AIRCRAFT
    global BRIGHTNESS, BRIGHTNESS_2, ACTIVE_PLANE_DISPLAY_BRIGHTNESS
    global CLOCK_CENTER_ROW, CLOCK_CENTER_ENABLED, CLOCK_CENTER_ROW_2ROWS
    global LED_PWM_BITS

    main_logger.info("Checking settings configuration...")

    if not NODISPLAY_MODE:
        try:
            if len(CLOCK_CENTER_ROW) != 2:
                raise KeyError
            for key in CLOCK_CENTER_ROW:
                if (CLOCK_CENTER_ROW[key] is not None and not isinstance(CLOCK_CENTER_ROW[key], int))\
                or (CLOCK_CENTER_ROW[key] is None or CLOCK_CENTER_ROW[key] == 0):
                    main_logger.info(f"{key} for Clock center readout is disabled.")
                    CLOCK_CENTER_ROW[key] = None # make it simple for us down the line
                elif CLOCK_CENTER_ROW[key] == 1:
                    main_logger.info(f"{key} for Clock center will display Sunrise/Sunset times.")
                elif CLOCK_CENTER_ROW[key] == 2:
                    main_logger.info(f"{key} for Clock center will display Receiver Stats.")
                elif CLOCK_CENTER_ROW[key] == 3:
                    main_logger.info(f"{key} for Clock center will display extended calendar info.")
                else:
                    main_logger.warning(f"{key} for Clock center has an invalid setting. Nothing will be displayed.")
                    CLOCK_CENTER_ROW[key] = None
        except KeyError:
            main_logger.warning("Clock center readout is not properly configured.")
            CLOCK_CENTER_ROW = default_settings['CLOCK_CENTER_ROW']

        if CLOCK_CENTER_ROW['ROW1'] is None and CLOCK_CENTER_ROW['ROW2'] is None:
            CLOCK_CENTER_ENABLED = False
            main_logger.info("Clock center readout is disabled.")
        else:
            CLOCK_CENTER_ENABLED = True

        if (isinstance(CLOCK_CENTER_ROW['ROW1'], int) and isinstance(CLOCK_CENTER_ROW['ROW2'], int))\
        or (CLOCK_CENTER_ROW['ROW1'] is None and isinstance(CLOCK_CENTER_ROW['ROW2'], int)):
            main_logger.info("Clock center readout has two rows enabled, using smaller font size.")
            CLOCK_CENTER_ROW_2ROWS = True

        if CLOCK_CENTER_ENABLED and (CLOCK_CENTER_ROW['ROW1'] == CLOCK_CENTER_ROW['ROW2']):
            main_logger.warning("Clock center readout options are the same. Reverting to only one row.")
            CLOCK_CENTER_ROW_2ROWS = False
            CLOCK_CENTER_ROW['ROW2'] = None

        if LED_PWM_BITS is None or not isinstance(LED_PWM_BITS, int) or (LED_PWM_BITS < 1 or LED_PWM_BITS > 11):
            main_logger.warning(f"LED_PWM_BITS is out of bounds or not an integer.")
            main_logger.info(f">>> Setting to default ({default_settings['LED_PWM_BITS']})")
            LED_PWM_BITS = default_settings['LED_PWM_BITS']

    if not NOFILTER_MODE:
        if not isinstance(RANGE, (int, float)):
            main_logger.warning(f"RANGE is not a number. Setting to default value ({default_settings['RANGE'] * distance_multiplier:.2f}{distance_unit}).")
            globals()['RANGE'] = round(default_settings['RANGE'] * distance_multiplier, 2)
        if not isinstance(HEIGHT_LIMIT, int):
            main_logger.warning(f"HEIGHT_LIMIT is not an integer. Setting to default value ({default_settings['HEIGHT_LIMIT'] * altitude_multiplier}{altitude_unit}).")
            globals()['HEIGHT_LIMIT'] = round(default_settings['HEIGHT_LIMIT'] * altitude_multiplier, 2)

        if not isinstance(LOCATION_TIMEOUT, int) or\
        (LOCATION_TIMEOUT < 15 or LOCATION_TIMEOUT > 60):
            main_logger.warning(f"LOCATION TIMEOUT is out of bounds or not an integer.")
            main_logger.info(f">>> Setting to default ({default_settings['LOCATION_TIMEOUT']})")
            LOCATION_TIMEOUT = default_settings['LOCATION_TIMEOUT']
        else:
            if LOCATION_TIMEOUT == 60:
                main_logger.info("Location timeout set to 60 seconds. This will match dump1090's behavior.")
            else:
                main_logger.info(f"Location timeout set to {LOCATION_TIMEOUT} seconds.")

        # set hard limits for range
        if RANGE > (20 * distance_multiplier):
            main_logger.warning(f"Desired range ({RANGE}{distance_unit}) is out of bounds. Limiting to {20 * distance_multiplier:.2f}{distance_unit}.")
            main_logger.info(">>> If you would like to see more aircraft, consider \'No Filter\' mode. Use the \'-f\' flag.")
            RANGE = round(20 * distance_multiplier, 2)
        elif RANGE < (0.2 * distance_multiplier):
            main_logger.warning(f"Desired range ({RANGE}{distance_unit}) is too low. Limiting to {0.2 * distance_multiplier:.2f}{distance_unit}.")
            RANGE = round(0.2 * distance_multiplier, 2)

        height_warning = f"Warning: Desired height cutoff ({HEIGHT_LIMIT}{altitude_unit}) is"
        if HEIGHT_LIMIT >= (275000 * altitude_multiplier):
            main_logger.warning(f"{height_warning} beyond the theoretical limit for flight.")
            main_logger.info(f">>> Setting to a reasonable value:{75000 * altitude_multiplier:.2f}{altitude_unit}")
            HEIGHT_LIMIT = round(75000 * altitude_multiplier, 2)
        elif HEIGHT_LIMIT > (75000 * altitude_multiplier) and HEIGHT_LIMIT < (275000 * altitude_multiplier):
            main_logger.warning(f"{height_warning} beyond typical aviation flight levels.")
            main_logger.info(f">>> Limiting to {75000 * altitude_multiplier:.2f}{altitude_unit}.")
            HEIGHT_LIMIT = round(75000 * altitude_multiplier, 2)
        elif HEIGHT_LIMIT < (1000 * altitude_multiplier):
            if HEIGHT_LIMIT <= 0:
                main_logger.warning(f"{height_warning} ground level or underground.")
                main_logger.warning("Aircraft won't be doing the thing aircraft do at that point (flying).")
            else:
                main_logger.warning(f"{height_warning} too low. Are aircraft landing on your house?")
            main_logger.info(f">>> Setting to a reasonable minimum: {1000 * altitude_multiplier:.2f}{altitude_unit}.")
            HEIGHT_LIMIT = round(1000 * altitude_multiplier, 2)
        main_logger.info(f"Filtering summary: <{RANGE:.2f}{distance_unit}, <{HEIGHT_LIMIT:.2f}{altitude_unit}.")
    else:
        RANGE = 10000
        HEIGHT_LIMIT = 275000
        LOCATION_TIMEOUT = 60
    
    if not isinstance(FLYBY_STALENESS, int) or (FLYBY_STALENESS < 1 or FLYBY_STALENESS >= 1440):
        main_logger.warning(f"Desired flyby staleness is out of bounds.")
        main_logger.info(f">>> Setting to default ({default_settings['FLYBY_STALENESS']})")
        FLYBY_STALENESS = default_settings['FLYBY_STALENESS']
    if NOFILTER_MODE and FLYBY_STALENESS < 60:
        main_logger.info(f"No Filter mode enabled, flyby staleness now set to 60 minutes.")
        FLYBY_STALENESS = 60

    if FOLLOW_THIS_AIRCRAFT:
        try:
            test1 = int(FOLLOW_THIS_AIRCRAFT, 16) # check if this produces a valid number
            if len(FOLLOW_THIS_AIRCRAFT) != 6 or test1 < 0:
                raise ValueError
            del test1
            FOLLOW_THIS_AIRCRAFT = FOLLOW_THIS_AIRCRAFT.lower() # json file has the hex IDs in lowercase
            main_logger.info(f"FOLLOW_MODE enabled: Aircraft with hex ID \'{FOLLOW_THIS_AIRCRAFT}\' will be shown when detected by the ADS-B receiver.")
        except (ValueError, TypeError):
            main_logger.warning("FOLLOW_THIS_AIRCRAFT is not a valid hex ID.")
            main_logger.info(">>> Disabling FOLLOW_MODE.")
            FOLLOW_THIS_AIRCRAFT = ""
    else:
        FOLLOW_THIS_AIRCRAFT = ""

    if not FLYBY_STATS_ENABLED:
        main_logger.info("Flyby stats will not be written.")

    brightness_list = ["BRIGHTNESS", "BRIGHTNESS_2", "ACTIVE_PLANE_DISPLAY_BRIGHTNESS"]
    for setting_entry in brightness_list:
        try:
            imported_value = globals()[f"{setting_entry}"] # get current imported setting value
            if setting_entry == "ACTIVE_PLANE_DISPLAY_BRIGHTNESS" and imported_value is None:
                continue
            if not isinstance(imported_value, int) or (imported_value < 0 or imported_value > 100):
                main_logger.warning(f"{setting_entry} is out of bounds or not an integer.")
                main_logger.info(f">>> Using default value ({default_settings[setting_entry]}).")
                globals()[f"{setting_entry}"] = default_settings[setting_entry]
        except KeyError:
            pass

    if ALTERNATIVE_FONT:
        main_logger.info("Using the alternative font style.")

    if JOURNEY_PLUS:
        main_logger.info("JOURNEY_PLUS mode is enabled, enjoy the additional info.")

    if FASTER_REFRESH:
        main_logger.info("FASTER_REFRESH enabled, dump1090 polling rate is now 1 second.")

    if ORJSON_IMPORTED:
        main_logger.debug("orjson module imported and will be used for faster dump1090 json decoding.")

    if not WRITE_STATE:
        main_logger.info("FlightGazer will not write its state to a file.")

    main_logger.info("Settings check complete.")

def configuration_check_api() -> None:
    """ Check the API configuration. """
    global API_KEY, API_DAILY_LIMIT, api_usage_cost_baseline, API_COST_LIMIT, API_cost_limit_reached
    global ENHANCED_READOUT, ENHANCED_READOUT_INIT

    # check the API config
    main_logger.info("Checking API settings...")
    if not NOFILTER_MODE:
        if not isinstance(API_KEY, str):
            main_logger.warning("API key is invalid.")
            API_KEY = ""

        if (API_KEY and (
            API_DAILY_LIMIT is not None 
            and not isinstance(API_DAILY_LIMIT, int)
            )) or (
            isinstance(API_DAILY_LIMIT, int) 
            and API_DAILY_LIMIT <= 0):
                main_logger.warning("API_DAILY_LIMIT is invalid. Refusing to use API to prevent accidental overcharges.")
                API_DAILY_LIMIT = None
                API_KEY = ""
        
        if (API_KEY and (
            API_COST_LIMIT is not None 
            and not isinstance(API_COST_LIMIT, (float, int))
            )) or (
            isinstance(API_COST_LIMIT, (float, int))
            and API_COST_LIMIT <= 0):
                main_logger.warning("API_COST_LIMIT is invalid. Refusing to use API to prevent accidental overcharges.")
                API_COST_LIMIT = None
                API_KEY = ""

        # test if the API key works
        if API_KEY:
            api_use = None
            api_cost = None
            api_use, api_cost = probe_API()

            if api_use is None:
                main_logger.warning("Provided API Key failed to return a valid response.")
                API_KEY = ""
            else:
                main_logger.info(f"API Key \'***{API_KEY[-5:]}\' is valid.")
                main_logger.info(f">>> Stats from the past 30 days: {api_use} total calls, costing ${api_cost:.2f}.")
                api_usage_cost_baseline = api_cost

        if API_KEY: # test again
            if ENHANCED_READOUT:
                main_logger.info("ENHANCED_READOUT setting is enabled. API will not be used.")
            else:
                if ENHANCED_READOUT_AS_FALLBACK and DISPLAY_IS_VALID:
                    main_logger.info("ENHANCED_READOUT_AS_FALLBACK is enabled. When an API limit is reached, ENHANCED_READOUT will be used.")

                if API_DAILY_LIMIT is None:
                    main_logger.info("No daily limit set for API calls.")
                else:
                    main_logger.info(f"Limiting API calls to {API_DAILY_LIMIT} per day.")

                if API_COST_LIMIT is None:
                    main_logger.info("No cost limit set for API calls.")
                else:
                    if api_cost < API_COST_LIMIT:
                        main_logger.info(f"Limiting API calls to when usage is near ${API_COST_LIMIT:.2f}. (${API_COST_LIMIT - api_cost:.2f} available to use)")
                    else:
                        main_logger.warning(f"Current API usage (${api_cost}) exceeds set limit (${API_COST_LIMIT:.2f}).")
                        main_logger.info(">>> Disabling API.")
                        API_cost_limit_reached = True
                        API_KEY = ""

        else:
            main_logger.info("API is unavailable. Additional API-derived info will not be available.")
            if DISPLAY_IS_VALID:
                if ENHANCED_READOUT:
                    main_logger.info("Additional info provided by dump1090 will be substituted on display instead.")
                elif not ENHANCED_READOUT and not ENHANCED_READOUT_AS_FALLBACK:
                    main_logger.info("Setting ENHANCED_READOUT or ENHANCED_READOUT_AS_FALLBACK to \'true\' is highly recommended.")
                elif not ENHANCED_READOUT and ENHANCED_READOUT_AS_FALLBACK:
                    ENHANCED_READOUT = True
                    main_logger.info("ENHANCED_READOUT_AS_FALLBACK enabled, ENHANCED_READOUT is now forced to \'True\'.")
    else:
        main_logger.info("No Filter mode is enabled. API will not be used.")
    ENHANCED_READOUT_INIT = ENHANCED_READOUT

    main_logger.info("API check complete.")

def read_receiver_stats() -> None:
    """ Poll receiver stats from dump1090. Writes to `receiver_stats`.
    Needs to run on its own thread as its timing does not depend on `LOOP_INTERVAL`. """
    # inspired by https://github.com/wiedehopf/graphs1090/blob/master/dump1090.py
    if not DUMP1090_IS_AVAILABLE: return # don't start this thread if, only at startup, dump1090 is unavailable
    global receiver_stats

    while True:
        if watchdog_triggers > (watchdog_setpoint - 1):
            main_logger.debug("Watchdog has been triggered too many times. Terminating thread and disabling receiver stats.")
            with threading.Lock():
                receiver_stats['Gain'] = None
                receiver_stats['Noise'] = None
                receiver_stats['Strong'] = None
            break
        gain_now = None
        noise_now = None
        loud_percentage = None
        if DUMP1090_IS_AVAILABLE:
            try:
                if USING_FILESYSTEM:
                    with open(Path(URL + '/stats.json'), 'rb') as stats_file:
                        if ORJSON_IMPORTED:
                            stats = orjson.loads(stats_file.read())
                        else:
                            stats = json.load(stats_file)
                else:
                    receiver_req = session.get(URL + '/data/stats.json', headers=USER_AGENT, timeout=5)
                    receiver_req.raise_for_status()
                    receiver_data = receiver_req.content
                    if ORJSON_IMPORTED:
                        stats = orjson.loads(receiver_data)
                    else:
                        stats = json.loads(receiver_data)
                    
                if has_key(stats, 'last1min'):
                    try:
                        noise_now = stats['last1min']['local']['noise']
                    except KeyError:
                        noise_now = None
                    try:
                        messages1min = stats['last1min']['messages']
                        loud_messages = stats['last1min']['local']['strong_signals']
                        if messages1min == 0:
                            loud_percentage = 0
                        else:
                            loud_percentage = round((loud_messages / messages1min) * 100, 3)
                    except KeyError:
                        loud_percentage = None
                else:
                    noise_now = None
                    loud_percentage = None
                    
                if has_key(stats, 'gain_db'):
                    gain_now = stats['gain_db']
                else:
                    gain_now = None
                
            except:
                pass

        with threading.Lock():
            receiver_stats['Gain'] = gain_now
            receiver_stats['Noise'] = noise_now
            receiver_stats['Strong'] = loud_percentage
        time.sleep(5) # don't need to poll too often

def suntimes() -> None:
    """ Update sunrise and sunset times """
    global sunset_sunrise
    if rlat is not None and rlon is not None:
        sun = Sun(rlat, rlon)
        time_now = datetime.datetime.now().astimezone()
        try:
            sunset_sunrise['Sunrise'] = sun.get_sunrise_time(time_now).astimezone()
            sunset_sunrise['Sunset'] = sun.get_sunset_time(time_now).astimezone()
            if sunset_sunrise['Sunset'] < sunset_sunrise['Sunrise']:
                main_logger.debug("suntimes bug present, correcting sunset time.")
                sunset_sunrise['Sunset'] += datetime.timedelta(days=1)
        except SunTimeException:
            sunset_sunrise['Sunrise'] = None
            sunset_sunrise['Sunset'] = None
    else:
        sunset_sunrise['Sunrise'] = None
        sunset_sunrise['Sunset'] = None
    main_logger.debug(f"Sunrise: {sunset_sunrise['Sunrise']}, Sunset: {sunset_sunrise['Sunset']}")

def timesentinel() -> None:
    """ Thread that watches for time changes (eg: system time changes after a reboot, DST, etc) """
    while True:
        time_now = datetime.datetime.now()
        time.sleep(1)
        timechange = (datetime.datetime.now() - time_now).total_seconds() - 1
        if abs(timechange) > 5:
            main_logger.info(f"Time has been changed by {timechange:.1f} seconds.")

# =========== Program Setup III ============
# ===========( Core Functions )=============
    
def flyby_stats() -> None:
    """
    If `FLYBY_STATS_ENABLED` is true, write the gathered stats from our flybys to a csv file. 
    When this is run for the first time, it will check if `FLYBY_STATS_FILE` exists and sets appropriate flags.
    If `FLYBY_STATS_FILE` is valid, subsequent calls to this function will append data to the end of it.
    This function assumes it will be called hourly to keep track of stats thoughout the day.
    Written values are accumulative and are reset at midnight.
    """
    global flyby_stats_present, FLYBY_STATS_ENABLED
    if not FLYBY_STATS_ENABLED:
        return
    header = "Date,Number of flybys,API calls (successful),API calls (failed),API calls (empty)\n"
    if FLYBY_STATS_FILE.is_file() and not flyby_stats_present:
        with open(FLYBY_STATS_FILE, 'r') as stats: # check if the file has a valid header
            head = next(stats)
            if head == header:
                flyby_stats_present = True
                main_logger.info(f"Flyby stats file \'{FLYBY_STATS_FILE}\' is present.")
            else:
                main_logger.warning(f"Header in \'{FLYBY_STATS_FILE}\' is incorrect or has been modifed. Stats will not be saved.")
                FLYBY_STATS_ENABLED = False

        # load in last line of stats file, check if today's the current date, and re-populate our running stats
        if flyby_stats_present:
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
                global api_hits, unique_planes_seen, estimated_api_cost
                planes_seen = int(last_line.split(",")[1])
                api_hits[0] = int(last_line.split(",")[2])
                api_hits[1] = int(last_line.split(",")[3])
                api_hits[2] = int(last_line.split(",")[4])
                estimated_api_cost = API_COST_PER_CALL * (api_hits[0] + api_hits[2])
                for i in range(planes_seen): # fill the set with filler values, we don't recall the last contents of `unique_planes_seen`
                    unique_planes_seen.append(
                        {"ID":i+1,
                         "Time":time.monotonic(),
                        }
                         )
                main_logger.info(f"Successfully reloaded last written data for {date_now_str}. Flybys: {planes_seen}. API calls: {api_hits[0] + api_hits[2]}")
        return
    
    elif not FLYBY_STATS_FILE.is_file():
        try:
            Path(FLYBY_STATS_FILE).touch(mode=0o777)
            with open(FLYBY_STATS_FILE, 'w') as stats:
                stats.write(header)
            main_logger.info(f"No Flyby stats file was found. A new flyby stats file \'{FLYBY_STATS_FILE}\' was created.")
            flyby_stats_present = True
            return
        except:
            main_logger.error(f"Cannot write to \'{FLYBY_STATS_FILE}\'. Stats will not be saved.")
            FLYBY_STATS_ENABLED = False
            return

    if flyby_stats_present:
        date_now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        try:
            with open(FLYBY_STATS_FILE, 'a') as stats:
                stats.write(f"{date_now_str},{len(unique_planes_seen)},{api_hits[0]},{api_hits[1]},{api_hits[2]}\n")
        except:
            main_logger.error(f"Cannot write to \'{FLYBY_STATS_FILE}\'. Data for {date_now_str} has been lost.")
    return

def print_to_console() -> None:
    """ This is for testing/viewing internal logic. Note: this is summoned by `AirplaneParser`
    as it is expected that all the variables will have their end-of-loop values written at the end of execution. """
    global this_process_cpu
    plane_count = len(relevant_planes)
    run_time = time.monotonic() - START_TIME
    time_print = f"{datetime.datetime.now()}".split(".")[0]
    ver_str = VERSION.split(" --- ")[0]

    rst = "\x1b[0m"
    fade = "\x1b[2m"
    italic = "\x1b[3m"
    white_highlight = "\x1b[0;30;47m"
    red_warning = "\x1b[0;30;41m"
    yellow_warning = "\x1b[0;30;43m"
    green_highlight = "\x1b[0;30;42m"
    blue_highlight = "\x1b[0;37;44m"
    yellow_text = "\x1b[0;33m"

    cls()
    # header section
    print(f"{rst}{green_highlight}===== FlightGazer {ver_str} Console Output ====={rst} {fade}Time now: {time_print} | Runtime: {timedelta_clean(run_time)}{rst}")
    if not DUMP1090_IS_AVAILABLE:
        if watchdog_triggers == 0:
            print(f"{red_warning}********** dump1090 did not successfully load. There will be no data! **********{rst}\n")
            print(f"{white_highlight}Please check your settings, your network connection, and the status of dump1090. Then, restart FlightGazer.{rst}")
        elif watchdog_triggers > 0 and watchdog_triggers < watchdog_setpoint:
            print(f"{yellow_warning}***** Watchdog triggered. There is currently a pause on {dump1090} processing. *****{rst}\n")
        elif watchdog_triggers >= watchdog_setpoint:
            print(f"{red_warning}***** {dump1090} connection is too unstable! No more data will be processed! *****{rst}")
            print(f"         {white_highlight}Please correct the underlying issue then restart FlightGazer.{rst}\n")

    if DUMP1090_IS_AVAILABLE and (rlat is None or rlon is None) and not NOFILTER_MODE:
        print(f"{yellow_warning}********** Location is not set! No aircraft information will be shown! **********{rst}\n")

    if not DISPLAY_IS_VALID and not NODISPLAY_MODE:
        print(f"{red_warning}**********       Display output is unavailable.     **********{rst}\n")

    if DUMP1090_IS_AVAILABLE:
        if not NOFILTER_MODE:
            if not FOLLOW_THIS_AIRCRAFT:
                print(f"{fade}Filters enabled: <{RANGE}{distance_unit}, <{HEIGHT_LIMIT}{altitude_unit}{rst}")
            else:
                print(f"{fade}Filters enabled: <{RANGE}{distance_unit}, <{HEIGHT_LIMIT}{altitude_unit}, or \'{FOLLOW_THIS_AIRCRAFT}\'{rst}")
        else:
            print(f"{white_highlight}******* No Filters mode enabled. All aircraft with locations detected by {dump1090} shown. *******{rst}\n")

    if focus_plane_iter != 0:
        # reflects plane selection algorithm
        select_divisor = 1
        if plane_count == 2:
            select_divisor = plane_latch_times[0]
        elif plane_count == 3:
            select_divisor = plane_latch_times[1]
        elif plane_count >= 4:
            select_divisor = plane_latch_times[2]
        next_select = ((focus_plane_iter // select_divisor) + 1) * select_divisor

        if plane_count == 1:
            print(f"{fade}[Inside focus loop {focus_plane_iter}]{rst}\n")
        else:
            print(f"{fade}[Inside focus loop {focus_plane_iter}, next switch on loop {next_select}, watching: {white_highlight}\'{focus_plane}\'{rst}\n")
        if len(focus_plane_ids_scratch) > 0:
            print(f"{fade}Aircraft scratchpad: {focus_plane_ids_scratch}{rst}")
        elif len(focus_plane_ids_scratch) == 0:
            print(f"{fade}Aircraft scratchpad: {{}}{rst}")

    # aircraft readout section
    for a, aircraft in enumerate(relevant_planes):
        try:
            print_info = []
            print_info.append(f"{rst}")
            # algorithm indicators
            if not NOFILTER_MODE:
                if focus_plane == aircraft['ID']:
                    print_info.append(white_highlight)
                # else:
                #     print_info.append("  ")
                if focus_plane_ids_discard:
                    if aircraft['ID'] in focus_plane_ids_discard:
                        print_info.append(italic)
                    # else:
                    #     print_info.append("  ")
            
            if FOLLOW_THIS_AIRCRAFT == aircraft['ID']:
                print_info.append("--> ")
            
            # counter, callsign, iso, id
            print_info.append("[{a:03d}] {flight} ({iso}, {id})".format(
                a = a+1,
                flight = f"{aircraft['Flight']}".ljust(8),
                iso = aircraft['Country'],
                id = f"{aircraft['ID']}".ljust(6)
            ))
            print_info.append(" | ")

            # speed section
            print_info.append("SPD: ")
            print_info.append("{gs:.1f}".format(gs = aircraft['Speed']).rjust(5))
            print_info.append(f"{speed_unit} @ ")
            print_info.append("{track:.1f}°".format(track = aircraft['Track']).rjust(6))
            print_info.append(" | ")
            # altitude section
            print_info.append("ALT: ")
            print_info.append("{alt:.1f}".format(alt = aircraft['Altitude']).rjust(7))
            print_info.append(f"{altitude_unit}, ")
            print_info.append("{vs:.1f}".format(vs = aircraft['VertSpeed']).rjust(7))
            print_info.append(f"{altitude_unit}/min, ")
            print_info.append("{elevation:.2f}°".format(elevation = aircraft['Elevation']).rjust(6))
            print_info.append(" | ")
            # distance section
            print_info.append(f"DIST: {aircraft['Direction']}")
            print_info.append("{distance:.2f}".format(distance=aircraft['Distance']).rjust(6))
            print_info.append(f"{distance_unit} ")
            print_info.append("LOS")
            print_info.append("{slant_range:.2f}".format(slant_range=aircraft['SlantRange']).rjust(6))
            print_info.append(f"{distance_unit} ")
            print_info.append("({lat:.3f}, {lon:.3f})".format(
                lat=aircraft['Latitude'],
                lon=aircraft['Longitude'],
            ).ljust(16))
            print_info.append(" | ")
            # last section
            print_info.append("RSSI: ")
            print_info.append("{rssi}".format(rssi = aircraft['RSSI']).rjust(5))
            print_info.append("dBFS")

            # finally, print it all
            print_info.append(rst)
            print("".join(print_info))

        except: # gracefully handle where it breaks
            main_logger.debug("Print routine could not read all the data. Is the system thrashing?")
            print("", flush=True)
            print(f"{yellow_warning}< Could not finish reading all data >{rst}")
            break
     
    for i in range(len(focus_plane_api_results)): # only shows if API has something to show
        try:
            if focus_plane_api_results[-i-1] is not None and focus_plane == focus_plane_api_results[-i-1]['ID']:
                api_flight = focus_plane_api_results[-i-1]['Flight']
                api_orig = focus_plane_api_results[-i-1]['Origin']
                if api_orig is None: api_orig = "?"
                api_dest = focus_plane_api_results[-i-1]['Destination']
                if api_dest is None: api_dest = "?"
                api_dpart_time = focus_plane_api_results[-i-1]['Departure']
                if api_dpart_time is not None:
                    api_dpart_delta = strfdelta((datetime.datetime.now(datetime.timezone.utc) - api_dpart_time), "{H}h{M:02}m")
                else:
                    api_dpart_delta = "?"
                print(f"\n{blue_highlight}API results for {white_highlight}{api_flight}{blue_highlight}: \
[ {api_orig} ] --> [ {api_dest} ], {api_dpart_delta} flight time{rst}")
                break
        except: # if we bump into None or something else
            break

    # process `receiver_stats`
    gain_str = "N/A"
    noise_str = "N/A"
    loud_str = "N/A"
    if receiver_stats['Gain'] is not None:
        gain_str = f"{receiver_stats['Gain']}dB"
    if receiver_stats['Noise'] is not None:
        noise_str = f"{receiver_stats['Noise']}dB"
    if receiver_stats['Strong'] is not None:
        loud_str = f"{receiver_stats['Strong']:.1f}%"

    # collate general info 
    gen_info = []
    gen_info_str = ""
    if VERBOSE_MODE:
        if DUMP1090_IS_AVAILABLE:
            gen_info.append("> ")
            gen_info.append(f"dump1090: {URL}")
            if DUMP978_JSON is not None:
                gen_info.append(", dump978: ")
                if USING_FILESYSTEM_978:
                    gen_info.append(f"{DUMP978_JSON[:-14]}")
                else:
                    gen_info.append(f"{DUMP978_JSON[:-19]}")
            if HOSTNAME:
                gen_info.append(f" | Running on {CURRENT_IP}")
                if CURRENT_IP:
                    gen_info.append(f" as {HOSTNAME}")
            gen_info_str = "".join(gen_info)
        else:
            if HOSTNAME:
                gen_info.append(f"> Running on {CURRENT_IP}")
                if CURRENT_IP:
                    gen_info.append(f" as {HOSTNAME}")
            gen_info_str = "".join(gen_info)

    # print footer section
    main_stat = []
    main_stat.append(f"\n{rst}{fade}> {dump1090}")
    if DUMP978_JSON is not None:
        main_stat.append("+dump978")
    main_stat.append(f" response {process_time[0]:.3f} ms | ")
    main_stat.append(f"Processing {(process_time[1]+process_time2[1]+process_time2[2]):.3f} ms | ")
    if not NODISPLAY_MODE:
        main_stat.append(f"Avg frame render {process_time[3]:.3f} ms, {display_fps:.1f} FPS")
    else:
        main_stat.append(f"Last console print {process_time2[0]:.3f} ms")
    if API_KEY:
        main_stat.append(f" | Last API response {process_time[2]:.3f} ms")
    main_stat_str = "".join(main_stat)
    print(main_stat_str)
    
    verbose_stats = []
    verbose_str = ""
    if VERBOSE_MODE:
        verbose_stats.append("> ")
        if not NODISPLAY_MODE:
            verbose_stats.append(f"Last console print {process_time2[0]:.3f} ms | ")
        verbose_stats.append(f"Display formatting {process_time2[1]:.3f} ms | ")
        verbose_stats.append(f"json parsing {process_time2[2]:.3f} ms | ")
        verbose_stats.append(f"Filtering+algorithm {process_time[1]:.3f} ms")
        verbose_str = "".join(verbose_stats)
        print(verbose_str)

    print(f"> Detected {general_stats['Tracking']} aircraft, {plane_count} aircraft in range, max range: {general_stats['Range']:.2f} {distance_unit} | \
Gain: {gain_str}, Noise: {noise_str}, Strong signals: {loud_str}")
    
    if API_KEY:
        if not API_daily_limit_reached and not API_cost_limit_reached:
            print(f"> API stats for today: {api_hits[0]} success, {api_hits[1]} fail, {api_hits[2]} no data, {api_hits[3]} cache hits | \
Estimated cost: ${estimated_api_cost:.2f}")
        elif API_daily_limit_reached:
            print(f"> API daily limit ({API_DAILY_LIMIT}) reached. No more API calls for the rest of today.")
        elif API_cost_limit_reached:
            print(f"> {rst}{yellow_text}API cost limit (${API_COST_LIMIT:.2f}) reached. API calls have stopped.{rst}{fade}")

    if not VERBOSE_MODE:
        print(f"> Total flybys today: {len(unique_planes_seen)} | Aircraft selections: {selection_events}")
    else:
        print(f"> Total flybys today: {len(unique_planes_seen)} | Aircraft selections: {selection_events} | \
Rare events from algorithm: {algorithm_rare_events}")

    current_memory_usage = psutil.Process().memory_info().rss
    this_process_cpu = this_process.cpu_percent(interval=None)
    if CPU_TEMP_SENSOR is not None:
        cpu_temp = psutil.sensors_temperatures()[CPU_TEMP_SENSOR][0].current
        print(f"> CPU & memory usage: {round(this_process_cpu / CORE_COUNT, 1)}% overall CPU @ {cpu_temp:.1f}°C | {round(current_memory_usage / 1048576, 3):.3f} MiB")
    else:
        print(f"> CPU & memory usage: {round(this_process_cpu / CORE_COUNT, 1)}% overall CPU | {round(current_memory_usage / 1048576, 3):.3f} MiB")

    json_details = []
    if VERBOSE_MODE:
        json_details.append(f"> json details: {runtime_sizes[0] / 1024:.3f} KiB")
        if process_time[0] != 0:
            json_details.append(f" | Transfer speed: {(runtime_sizes[0] * 1000)/(process_time[0] * 1048576):.3f} MiB/s | ")
        else:
            json_details.append(f" | Transfer speed: 0 MiB/s | ")
        if process_time2[2] != 0:
            json_details.append(f"Processing speed: {(runtime_sizes[0] * 1000)/(process_time2[2] * 1048576):.3f} MiB/s")
        else:
            json_details.append(f"Processing speed: 0 MiB/s")
        if WRITE_STATE:
            json_details.append(f" | Export processing: {process_time2[3]:.3f} ms")
        print("".join(json_details))

    if dump1090_failures > 0:
        print(f">{rst}{yellow_text} {dump1090} communication failures since start: {dump1090_failures} | Watchdog triggers: {watchdog_triggers}{rst}{fade}")
    
    if VERBOSE_MODE and display_failures > 0:
        print(f">{rst}{yellow_text} Display failures: {display_failures}{rst}{fade}")

    if VERBOSE_MODE:
        print(gen_info_str)

    if INSIDE_TMUX:
        print(f">{italic} Use \'Ctrl+B D\' to detach from this session. Ctrl+C to exit -and- quit FlightGazer.{rst}")
    else:
        print(f">{italic} Ctrl+C to exit -and- quit FlightGazer. Closing this window will uncleanly terminate FlightGazer.{rst}")

def main_loop_generator() -> None:
    """ Our main `LOOP` generator. Only generates/publishes data for subscribers to interpret.
    (an homage to Davis Instruments `LOOP` packets for their weather stations) """

    def flyby_tracker(input_ID: str) -> None:
        """ Adds given plane ID to `unique_planes_seen` list. """
        global unique_planes_seen
        def add_entry() -> None:
            with threading.Lock():
                unique_planes_seen.append(
                    {"ID": input_ID,
                    "Time": time.monotonic()
                    }
                )
        entry_count = len(unique_planes_seen)
        # limit search to the following amount for speed reasons (<~0.5ms);
        # it's assumed that if a previously seen plane appears again and
        # there have already been these many flybys, it's already stale
        limit_count = 500
        stale_age = FLYBY_STALENESS * 60 # seconds
        if entry_count > limit_count: entry_count = limit_count
        
        # special case when there aren't any entries yet
        if len(unique_planes_seen) == 0:
            add_entry()
            return
        
        for a in range(entry_count):
            # search backwards through list
            if unique_planes_seen[-a-1]['ID'] == input_ID:
                if time.monotonic() - unique_planes_seen[-a-1]['Time'] > stale_age:
                    add_entry()
                    return
                else: # if we recently have seen this plane
                    return
        else: # finally, if we don't find the entry, add a new one
            add_entry()
            return
    
    def relative_direction(**kwargs) -> str:
        """ Gets us the plane's relative cardinal direction in respect to our location.
        Supply a `rdir` angle value to skip internal calculation. If `rdir` is None, supply `lat0`, `lon0`, `lat1`, `lon1`.
        Sourced from here: https://gist.github.com/RobertSudwarts/acf8df23a16afdb5837f?permalink_comment_id=3070256#gistcomment-3070256 """
        dirs = ['N ', 'NE', 'E ', 'SE', 'S ', 'SW', 'W ', 'NW'] # note the spaces for 1 letter directions
        # dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        d = kwargs.get('rdir')
        if d is None:
            try:
                d = math.atan2((kwargs['lon1'] - kwargs['lon0']), (kwargs['lat1'] - kwargs['lat0'])) * (180 / math.pi)
            except:
                return ""
        ix = round(d / (360. / len(dirs)))
        return dirs[ix % len(dirs)]
    
    def greatcircle(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
        """ Calculates distance between two points on Earth based on their latitude and longitude.
        (returns value based on selected units) """
        lat0 = lat0 * math.pi / 180.0
        lon0 = lon0 * math.pi / 180.0
        lat1 = lat1 * math.pi / 180.0
        lon1 = lon1 * math.pi / 180.0
        # Earth arithmetic mean radius defined by the IUGG in nautical miles = 3440
        earth_radius = 3440 * distance_multiplier
        return earth_radius * math.acos(math.sin(lat0) * math.sin(lat1) + math.cos(lat0) * math.cos(lat1) * math.cos(abs(lon1 - lon0)))
    
    def elevation_and_slant(greatcircle_dist: float, altitude: float) -> tuple[float, float]:
        """ Calculates elevation angle and slant range based on given distance and altitude.
        NB: this function assumes the site elevation is 0 relative to the target, eg,
        we are looking at the local horizon. Additionally, this returns the 'real'
        elevation angle and line-of-sight distance unaffected by atmospheric conditions 
        as we already have a generally accurate location of the target.
        Excellent reference: https://www.ngs.noaa.gov/CORS/Articles/SolerEisemannJSE.pdf """
        if greatcircle_dist <= 0:
            return 0., 0.
        # calculate apparent drop in height to account for Earth's curvature, with radius in nautical miles
        drop_in_height = 3440 * (1 - math.cos(greatcircle_dist / (3440 * distance_multiplier)))
        # normalize all measurements to nautical miles; 6076.115 = feet per nautical mile
        dist_nm = (greatcircle_dist / distance_multiplier)
        alt_nm = altitude / (altitude_multiplier * 6076.115)
        alt_apparent = alt_nm - drop_in_height
        slant_range = math.sqrt(dist_nm**2 + alt_nm**2)
        return round(math.degrees(math.atan2(alt_apparent, dist_nm)), 6), round(slant_range * distance_multiplier, 6)

    def dump1090_heartbeat() -> list | None:
        """ Checks if dump1090 service is up and returns the relevant json file(s). If service is down/times out, returns None.
        Most of the processing time occurs here. This function is also the most vital for FlightGazer's normal operation. """
        if not DUMP1090_IS_AVAILABLE: return None
        global process_time, process_time2, runtime_sizes
        try:
            dump1090_start = time.perf_counter()
            if USING_FILESYSTEM:
                with open(Path(DUMP1090_JSON), 'rb') as dump1090_data:
                    # doing this is slightly slower (~5%) than just doing json.load(dump1090_data)
                    # we do it this way just for the "response" stat
                    s = dump1090_data.read()
                    process_time[0] = round((time.perf_counter() - dump1090_start) * 1000, 3)
                    runtime_sizes[0] = len(s)
                    # runtime_sizes[1] = sys.getsizeof(s)
                    json_parse1 = time.perf_counter()
                    if ORJSON_IMPORTED:
                        aircraft_data = orjson.loads(s)
                    else:
                        aircraft_data = json.loads(s)
                    process_time2[2] = round((time.perf_counter() - json_parse1) * 1000, 3)
            else:
                dump1090_req = session.get(DUMP1090_JSON, headers=USER_AGENT, timeout=LOOP_INTERVAL * 0.9)
                dump1090_req.raise_for_status()
                process_time[0] = round((time.perf_counter() - dump1090_start) * 1000, 3)
                runtime_sizes[0] = len(dump1090_req.content)
                # runtime_sizes[1] = sys.getsizeof(dump1090_req)
                json_parse1 = time.perf_counter()
                dump1090_data = dump1090_req.content
                if ORJSON_IMPORTED:
                    aircraft_data = orjson.loads(dump1090_data)
                else:
                    aircraft_data = json.loads(dump1090_data)
                process_time2[2] = round((time.perf_counter() - json_parse1) * 1000, 3)

            if DUMP978_JSON is not None:
                dump978_start = time.perf_counter()
                if USING_FILESYSTEM_978:
                    with open(Path(DUMP978_JSON), 'rb') as dump978_data:
                        s = dump978_data.read()
                        process_time[0] = process_time[0] + round((time.perf_counter() - dump978_start) * 1000, 3)
                        runtime_sizes[0] += len(s)
                        # runtime_sizes[1] += sys.getsizeof(s)
                        json_parse2 = time.perf_counter()
                        if ORJSON_IMPORTED:
                            aircraft_data2 = orjson.loads(s)
                        else:
                            aircraft_data2 = json.loads(s)
                else:
                    dump978_req = session.get(DUMP978_JSON, headers=USER_AGENT, timeout=LOOP_INTERVAL * 0.9)
                    process_time[0] = process_time[0] + round((time.perf_counter() - dump978_start) * 1000, 3)
                    dump978_req.raise_for_status() 
                    runtime_sizes[0] += len(dump978_req.content)
                    # runtime_sizes[1] += sys.getsizeof(dump978_req)
                    json_parse2 = time.perf_counter()
                    dump978_data = dump978_req.content
                    if ORJSON_IMPORTED:
                        aircraft_data2 = orjson.loads(dump978_data)
                    else:
                        aircraft_data2 = json.loads(dump978_data)
                aircraft_data['aircraft'].extend(aircraft_data2['aircraft']) # append dump978 json into dump1090 data
                process_time2[2] = process_time2[2] + round((time.perf_counter() - json_parse2) * 1000, 3)
                # if VERBOSE_MODE:
                #     runtime_sizes[1] += sys.getsizeof(aircraft_data)

            return aircraft_data
        except Exception as e:
            main_logger.debug(f"Error decoding json ({e})", exc_info=False)
            return None

    def dump1090_loop(dump1090_data: list) -> tuple[dict, list]:
        """ Our dump1090 json filter and internal formatter. Must be fed by a valid `dump1090_heartbeat()` response.
        Returns a dictionary and a list.
        - dictionary: general stats to be updated per loop.
            - Tracking = total planes being tracked at current time
            - Range = maximum range of tracked planes from your location (in selected units)
        - list: list of nested dictionaries that describes each plane found within `HEIGHT_LIMIT` and `RANGE` and updates per loop.
        If no planes are found or location is not set, this will return an empty list.
            - ID: ICAO hex of airplane
            - Flight: Callsign (falls back to registration and finally hex)
            - Country: Returns two letter ISO code based on ICAO hex
            - Altitude: Plane's altitude in the selected units. Returns 0 if can't be determined or if the plane is on the ground.
            - Speed: Plane's ground speed in selected units. Returns 0 if can't be determined.
            - Distance: Plane's distance from your location in the selected units. Returns 0 if location is not defined.
            - Direction: Cardinal direction of plane in relation to your location. Returns an empty string if location is not defined.
            - Latitude
            - Longitude
            - Track: Plane's track over ground in degrees
            - VertSpeed: Plane's rate of barometric altitude in units/minute
            - RSSI: Plane's average signal power in dBFS
            - Elevation: Plane's elevation angle in degrees
            - SlantRange: Plane's direct line-of-sight distance from your location in the selected units.
        """
        # refer to https://github.com/wiedehopf/readsb/blob/dev/README-json.md on relevant json keys

        if dump1090_data is None: return {'Tracking': 0, 'Range': 0}, []
        total: int = 0
        max_range: float = 0
        ranges = []
        planes = []
        unique_ids = set()
        
        try:
            for a in dump1090_data['aircraft']:
                seen_pos = a.get('seen_pos')
                broadcast_type = a.get('type')
                hex = a.get('hex', "?")
                # skip duplicate entries:
                # only accept the the first entry found of each unique ICAO hex, even if a better one is found
                # thus, with a combined ADS-B and UAT feed, ADS-B will prevail as UAT entries are appended at the end of `dump1090_data`
                if hex in unique_ids and not NOFILTER_MODE: continue
                unique_ids.add(hex)
                # filter planes that have valid tracking data and were seen recently
                if seen_pos is None\
                    or seen_pos > LOCATION_TIMEOUT\
                    or broadcast_type == 'tisb_other':
                    continue
                total +=1
                lat = a.get('lat')
                lon = a.get('lon')
                if rlat is not None and rlon is not None:
                    # readsb does this calculation already, try to use it first
                    distance = a.get('r_dst', greatcircle(rlat, rlon, lat, lon))
                else:
                    distance = 0
                ranges.append(distance)
                if NOFILTER_MODE or\
                   hex == FOLLOW_THIS_AIRCRAFT or\
                   (not NOFILTER_MODE and (distance < RANGE and distance > 0)):
                    alt = a.get('alt_geom', a.get('alt_baro'))
                    if alt is None or alt == "ground": alt = 0
                    alt = alt * altitude_multiplier
                    if alt < HEIGHT_LIMIT or hex == FOLLOW_THIS_AIRCRAFT:
                        flight = a.get('flight')
                        rssi = a.get('rssi', 0)
                        vs = a.get('geom_rate', a.get('baro_rate', 0))
                        vs = vs * altitude_multiplier
                        track = a.get('track', 0)
                        gs = a.get('gs', 0)
                        gs = gs * speed_multiplier
                        if rlat is not None:
                            # readsb also does this calculation, try to use it first and have the fallback ready
                            direc = relative_direction(
                                rdir = a.get('r_dir'),
                                lat0 = rlat,
                                lon0 = rlon,
                                lat1 = lat,
                                lon1 = lon)
                        else:
                            direc = ""
                        elevation, slant_range_dist = elevation_and_slant(distance, alt)
                        iso_code = flags.getICAO(hex).upper()
                        # This key is sometimes present in some readsb setups (eg: adsb.im images).
                        # Because it reads from a much more updated database, we try to use it first
                        registration = a.get('r', registrations.registration_from_hexid(hex))
                        if flight is None or flight == "        ": # when dump1090 reports an empty callsign, it will show 8 spaces
                            # fallback to registration, then ICAO hex
                            if registration is not None:
                                flight = registration
                            else:
                                flight = hex
                        else:
                            flight = flight.strip() # callsigns have ending whitespace; we need to remove for polling the API
                        planes.append(
                            {
                            "ID": hex,
                            "Flight": flight,
                            "Country": iso_code,
                            "Altitude": alt,
                            "Speed": gs,
                            "Distance": distance,
                            "Direction": direc,
                            "Latitude": lat,
                            "Longitude": lon,
                            "Track": track,
                            "VertSpeed": vs,
                            "RSSI": rssi,
                            "Elevation": elevation,
                            "SlantRange": slant_range_dist,
                            }
                        )
                        flyby_tracker(hex)

            if not ranges:
                max_range = 0
            else:
                max_range = round(max(ranges), 2)

            current_stats = {"Tracking": total, "Range": max_range}

        except: # just reuse the last data if an edge case is encountered
            current_stats = general_stats
            planes = relevant_planes

        return current_stats, planes
    
    def loop():
        """ Do the loop """
        global general_stats, relevant_planes, unique_planes_seen, process_time, dump1090_failures, process_time2, runtime_sizes
        while True:
            try:
                dump1090_data = dump1090_heartbeat()
                if not DUMP1090_IS_AVAILABLE:
                    process_time[0] = 0. # doesn't make sense for there to be a process time in this case
                    process_time2[2] = 0.
                if dump1090_data is None:
                    with threading.Lock():
                        general_stats = {'Tracking': 0, 'Range': 0.}
                        relevant_planes.clear()
                        runtime_sizes[0] = 0
                    if DUMP1090_IS_AVAILABLE: raise TimeoutError
                start_time = time.perf_counter()
                if DUMP1090_IS_AVAILABLE:
                    with threading.Lock():
                        general_stats, relevant_planes = dump1090_loop(dump1090_data)
                process_time[1] = round((time.perf_counter() - start_time)*1000, 3)

                dispatcher.send(message='', signal=DATA_UPDATED, sender=main_loop_generator)
                time.sleep(LOOP_INTERVAL) # our main loop polling time

            except TimeoutError:
                dump1090_failures += 1
                if INTERACTIVE:
                    cls()
                    print(f"FlightGazer: {dump1090} service timed out. This is occurrence {dump1090_failures}. Retrying...")
                if dump1090_failures % dump1090_failures_to_watchdog_trigger == 0:
                    main_logger.error(f"{dump1090} service has failed too many times ({dump1090_failures_to_watchdog_trigger}).")
                    dispatcher.send(message='', signal=KICK_DUMP1090_WATCHDOG, sender=main_loop_generator)
                else:
                    main_logger.warning(f"{dump1090} service timed out. This is occurrence {dump1090_failures}. Retrying...")
                time.sleep(5)
                continue

            except (SystemExit, KeyboardInterrupt):
                return

            except Exception as e:
                dump1090_failures += 1
                main_logger.error(f"LOOP thread caught an exception. ({e}) Trying again...")
                time.sleep(LOOP_INTERVAL * 5)
                continue

    # Enter here
    loop()

class AirplaneParser:
    """ When there are planes in `relevant_planes`, continuously parses plane list, selects an active plane (the algorithm), then triggers API fetcher.
    This thread is awoken every time `main_loop_generator.dump1090_loop()` updates data. This is the crux of FlightGazer's operation. """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        register_signal_handler(self.loop, self.plane_selector, signal=DATA_UPDATED, sender=main_loop_generator)
        register_signal_handler(self.loop, self.end_thread, signal=END_THREADS, sender=sigterm_handler)
        self._last_plane_count: int = 0
        """ Count of planes in `relevant_planes` from the previous loop """
        self.rare_occurrences: int = 0
        self._date_of_last_rare_message: str = ""
        self.run_loop()
    
    def plane_selector(self, message):
        """ Select a plane! """
        global focus_plane, focus_plane_stats, focus_plane_iter, focus_plane_ids_scratch, focus_plane_ids_discard
        global process_time, selection_events, algorithm_rare_events
        start_time = time.perf_counter()
        with threading.Lock():
            relevant_planes_local_copy = relevant_planes.copy()
        plane_count = len(relevant_planes_local_copy)
        get_plane_list: list = []
        focus_plane_i: str = ""
        date_now_str = datetime.datetime.now().strftime('%Y-%m-%d')
        # algorithm stuff; note how these are initialized before `focus_plane_iter` is incremented
        next_select_table = [0,0,0]
        loops_to_next_select = [0,0,0]
        for i, value in enumerate(plane_latch_times):
            next_select_table[i] = ((focus_plane_iter // value) + 1) * value
            loops_to_next_select[i] = value - (focus_plane_iter % value)

        def rare_message():
            """ Print a 'rare message' in the log. Under very specific conditions in real-world testing, this occurs up to 5% of the time. """
            self.rare_occurrences += 1
            if self.rare_occurrences <= 5:
                main_logger.info(f"Rare event! Aircraft count changed from {self._last_plane_count} to {plane_count} as we were about to select another one.")
                main_logger.debug(f">>> Occured on loop {focus_plane_iter} (selection event {selection_events + 1}) -> selection tables: {next_select_table} {loops_to_next_select}")
            if self.rare_occurrences == 5 and date_now_str == self._date_of_last_rare_message:
                main_logger.info("Traffic in the area is very high and the selection algorithm is being used extensively.")
                main_logger.info(">>> Suppressing further \'rare event\' messages for the rest of the day.")
                main_logger.info("    (Aircraft selection is still working normally)")
            self._date_of_last_rare_message = date_now_str

        def select():
            """ Our main plane selection algorithm. """
            """ 
            Programmer's Notes: The following selector algorithm is rather naive, but it works for occurrences when there is more than one plane in the area
            and we want to put some effort into trying to go through all of them without having to flip back and forth constantly at every data update.
            It is designed this way in conjunction with the `focus_plane_api_results` cache and `focus_plane_iter` modulo filters to minimize making new API calls.
            Additionally, it avoids the complications associated with trying to use a queue to handle `relevant_planes` per data update.
            The algorithm keeps track of already tracked planes and switches the focus to planes that haven't been tracked yet.
            `RANGE` should be relatively small giving us less possible concurrent planes to handle at a time, as the more planes are in the area,
            the higher the chance some planes will not be tracked whatsoever due to the latching time.
            
            A built-in metric on tracking the overall selection "efficiency" is by watching the value of 'Aircraft selections' in Interactive Mode introduced in v.2.4.0.
            The value should almost always be equal to or greater than the amount of flybys over the course of a day; a value lower than flybys means that some planes
            were not tracked whatsoever (very unlikely) or that FlightGazer was recently restarted and reinitialized to the last saved flyby count (more likely).
            A much higher value (1.5x-3x) is reflective of a very active area being monitored as the rate of switching increases to accommodate for increased traffic.
            """
            global focus_plane, focus_plane_ids_discard, focus_plane_ids_scratch
            with threading.Lock():
                focus_plane_ids_discard.add(focus_plane_i) # add previously assigned focus plane to scratchpad of planes to ignore
                discard_list = list(focus_plane_ids_discard)
                for id in discard_list: # remove all previously focused planes from the global list
                    focus_plane_ids_scratch.discard(id)
                scratch_list = list(focus_plane_ids_scratch)
                if len(focus_plane_ids_scratch) > 0:
                    focus_plane = random.choice(scratch_list) # get us the next plane from all remaining planes that were not tracked previously
                elif len(focus_plane_ids_scratch) == 0: # when we have cycled through all planes available, select another plane at random
                    whatever_else = get_plane_list.copy()
                    try:
                        whatever_else.remove(focus_plane_i) # remove the current focus plane from the list of planes to choose from
                    except ValueError:
                        pass
                    focus_plane = random.choice(whatever_else)
                    focus_plane_ids_discard.clear() # reset this set so that we can start cycling though planes again

        focus_plane_i = focus_plane # get previously assigned focus plane into this loop's copy

        if not NOFILTER_MODE:
            if plane_count > 0:
                if self._date_of_last_rare_message and date_now_str != self._date_of_last_rare_message: # reset count
                    if self.rare_occurrences >= 5:
                        main_logger.info(f"Re-enabling \'rare message\' printout.")
                    self.rare_occurrences = 0

                with threading.Lock():
                    focus_plane_ids_scratch.clear()
                    for a in range(plane_count):
                        get_plane_list.append(relevant_planes_local_copy[a]['ID']) # current planes in this loop 
                        focus_plane_ids_scratch.add(relevant_planes_local_copy[a]['ID']) # add the above to the global list (rebuilds each loop)
                            
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
                # switch focus plane only when modulo hits zero OR
                # if we were about to switch to another plane, but at this very loop
                # the plane count changes, which would throw off the modulo

                if ((plane_count > 1 and plane_count <= 4) and
                    self._last_plane_count > 1)\
                    and self._last_plane_count != plane_count:
                    # avoid times when the next select loop associated with the last plane count
                    # matches the next select loop associated with the current plane count
                    # due to the values being common multiples of each other
                    # eg: next_select_table = [150, 150, 156]
                    #                          ^    ^
                    #                          |    |
                    #                          |    +-- last plane count    | 3 planes
                    #                          +------- current plane count | 2 planes
                    last_plane_count_i = 4 if self._last_plane_count > 4 else self._last_plane_count # avoid IndexError
                    if (next_select_table[plane_count - 2] != next_select_table[last_plane_count_i - 2]):
                        if self._last_plane_count == 2 and loops_to_next_select[0] == 1:
                            select()
                            rare_message()
                        if self._last_plane_count == 3 and loops_to_next_select[1] == 1:
                            select()
                            rare_message()
                        if self._last_plane_count > 3 and loops_to_next_select[2] == 1:
                            select()
                            rare_message()
                else:
                    if plane_count == 2 and focus_plane_iter % plane_latch_times[0] == 0:
                        select()
                    if plane_count == 3 and focus_plane_iter % plane_latch_times[1] == 0:
                        select()
                    if plane_count > 3 and focus_plane_iter % plane_latch_times[2] == 0:
                        select()
                
                # finally, extract the plane stats to `focus_plane_stats` for use elsewhere
                with threading.Lock():
                    for i in range(min(plane_count, len(relevant_planes_local_copy))): # find our focus plane in `relevant_planes`
                        try:
                            if focus_plane == relevant_planes_local_copy[i]['ID']:
                                focus_plane_stats = relevant_planes_local_copy[i]
                                break
                        except IndexError:
                            main_logger.error(f"Plane selector failed to extract plane info.")
                            main_logger.error(f"Selection index: {i} | Relevant planes size: {len(relevant_planes)} | Selected plane: {focus_plane}")
                            main_logger.error(f"Relevant planes: {relevant_planes}")
                            focus_plane = ""
                            focus_plane_stats = dict()
                            break
                self._last_plane_count = plane_count

                # if this thread changed the focus plane, fire up the API fetcher
                if focus_plane_i != focus_plane:
                    selection_events += 1
                    dispatcher.send(message=focus_plane, signal=PLANE_SELECTED, sender=AirplaneParser.plane_selector)

            else: # when there are no planes
                if focus_plane: # clean-up variables
                    with threading.Lock():
                        focus_plane = ""
                        focus_plane_iter = 0
                        focus_plane_stats.clear()
                        focus_plane_ids_scratch.clear()
                        focus_plane_ids_discard.clear()
                        self._last_plane_count = 0
        
        with threading.Lock():
            process_time[1] = round(process_time[1] + (time.perf_counter() - start_time)*1000, 3)
            algorithm_rare_events = self.rare_occurrences
        
        dispatcher.send(message='', signal=PLANE_SELECTOR_DONE, sender=AirplaneParser.plane_selector)
        
        if INTERACTIVE:
            print_time_start = time.perf_counter()
            print_to_console()
            process_time2[0] = round((time.perf_counter() - print_time_start)*1000, 3)

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
        global process_time, focus_plane_api_results, api_hits, ENHANCED_READOUT
        global API_daily_limit_reached, estimated_api_cost, API_KEY, API_cost_limit_reached
        if API_KEY is None or not API_KEY: return
        if NOFILTER_MODE or ENHANCED_READOUT: return
        if API_daily_limit_reached or API_cost_limit_reached: return
        # get us our dates to narrow down how many results the API will give us
        date_now = datetime.datetime.now()
        time_delta_yesterday = date_now - datetime.timedelta(days=1)
        date_yesterday_iso = time_delta_yesterday.astimezone().replace(microsecond=0).isoformat()
        date_tomorrow = date_now + datetime.timedelta(days=1)
        date_tomorrow_iso = date_tomorrow.astimezone().replace(microsecond=0).isoformat()
        origin = None
        destination = None
        departure_time = None
        stale_age = FLYBY_STALENESS * 60 # seconds

        flight_id = focus_plane_stats.get('Flight', "")

        # if for some reason there is no flight ID, don't bother trying to query the API
        if not flight_id or flight_id == '?': return

        # check if we already have results
        for i in range(len(focus_plane_api_results)):
            try:
                if focus_plane_api_results[-i-1] is not None and\
                focus_plane == focus_plane_api_results[-i-1]['ID']: # cache hit: no need to query the API; reads deque from right to left
                    if time.monotonic() - focus_plane_api_results[-i-1]['APIAccessed'] < stale_age:
                        api_hits[3] += 1
                        return
                    else:
                        break
            except: # if we bump into None or something else
                break

        # our API call limiters
        if API_DAILY_LIMIT is not None and api_hits[0] >= API_DAILY_LIMIT:
            if not API_daily_limit_reached:
                # send this message only once until the limit is reset
                main_logger.info(f"API daily limit ({API_DAILY_LIMIT}) reached. No more API calls will occur until the next day.")
                API_daily_limit_reached = True
                process_time[3] = 0
                if ENHANCED_READOUT_AS_FALLBACK:
                    main_logger.info(">>> Enabling ENHANCED_READOUT mode as fallback.")
                    ENHANCED_READOUT = True # recall that once this is enabled, any call to this function will immediately return
            return
        
        # We use a 1 cent buffer just to account for any kind of calculation difference between
        # the actual API use and our running cost
        if API_COST_LIMIT is not None and (api_usage_cost_baseline + estimated_api_cost) >= (API_COST_LIMIT - 0.01):
            main_logger.warning(f"API cost limit (${API_COST_LIMIT}) reached. Disabling API usage.")
            main_logger.info(f"Estimated cost today: ${estimated_api_cost:.2f}")
            API_cost_limit_reached = True
            process_time[3] = 0
            if ENHANCED_READOUT_AS_FALLBACK:
                main_logger.info(">>> Enabling ENHANCED_READOUT mode as fallback.")
                ENHANCED_READOUT = True
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
            response = API_session.get(query_string, headers=auth_header, timeout=5)
            process_time[2] = round((time.perf_counter() - start_time)*1000, 3)
            response.raise_for_status()
            if response.status_code == 200: # check if service to the API call was valid
                response_json = response.json()
                # API reference -> https://www.flightaware.com/aeroapi/portal/documentation#get-/flights/-ident-
                if response_json['flights']: # if no results (ex: invalid flight_id or plane is blocked from tracking) this key will not exist
                    api_hits[0] += 1
                    main_logger.debug(f"API call for \'{flight_id}\' successful. Took {process_time[2]}ms")
                    for a in range(len(response_json['flights'])):
                        if "En Route" in response_json['flights'][a]['status']: # check we're reading current flight information
                            # check if these subkeys exist, if not, just return None
                            try:
                                # we optimally want the 3 letter airport codes
                                # cascade through these keys until we have something
                                origin: str | None = response_json['flights'][a]['origin']['code_lid']
                                if origin is None:
                                    origin = response_json['flights'][a]['origin']['code_iata']
                                if origin is None:
                                    origin = response_json['flights'][a]['origin']['code']
                            except: origin = None
                            try:
                                destination: str | None = response_json['flights'][a]['destination']['code_lid']
                                if destination is None:
                                    destination = response_json['flights'][a]['destination']['code_iata']
                                if destination is None:
                                    destination = response_json['flights'][a]['destination']['code']
                            except: destination = None
                            try:
                                depart_iso: str | None = response_json['flights'][a]['actual_off']
                                if depart_iso is None:
                                    departure_time = None
                                else:
                                    departure_time = depart_iso[:-1] + "+00:00" # API returns UTC time; need to format for .fromisoformat()
                                    departure_time = datetime.datetime.fromisoformat(departure_time)
                            except: departure_time = None
                            break
                else:
                    api_hits[2] += 1
                    main_logger.debug(f"API call for \'{flight_id}\' returned no useful data.")
            else:
                raise Exception
        except:
            api_hits[1] += 1
            main_logger.debug(f"API call for \'{flight_id}\' failed. Status code: {response.status_code}")
        finally:
            # special case when the API returns a coordinate instead of an airport
            # format is: "L 000.00000 000.00000" (no leading zeros, ordered latitude longitude)
            if origin is not None and origin.startswith("L "):
                main_logger.info(f"Rare event! API returned a coordinate origin ({origin}) for \'{flight_id}\'.")
                orig_coord = origin[2:].split(" ")
                lat = float(orig_coord[0])
                lon = float(orig_coord[1])
                if lat >= 0: lat_str = "N"
                elif lat <0: lat_str = "S"
                if lon >= 0: lon_str = "E"
                elif lon <0: lon_str = "W"
                origin = f"{abs(lat):.1f}{lat_str}"
                # Exploit the fact that since we are looking at a position-only flight there will be no known destination beforehand.
                # We replace the destination with the longitude instead for space reasons (worst case string length: 5 lat, 6 lon)
                destination = f"{abs(lon):.1f}{lon_str}"

            api_results = {
                'ID': focus_plane,
                'Flight': flight_id,
                'Origin': origin,
                'Destination': destination,
                'Departure': departure_time,
                'APIAccessed': time.monotonic()
                }
            with threading.Lock():
                estimated_api_cost = API_COST_PER_CALL * (api_hits[0] + api_hits[2])
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
    much like how `print_to_console()` displays its data. Additionally we control the layout switchover when `FOLLOW_THIS_AIRCRAFT`
    is enabled. """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        register_signal_handler(self.loop, self.data_packet, signal=PLANE_SELECTOR_DONE, sender=AirplaneParser.plane_selector)
        register_signal_handler(self.loop, self.end_thread, signal=END_THREADS, sender=sigterm_handler)
        self.run_loop()

    def data_packet(self, message):
        """ Every time `AirplaneParser.plane_selector` finishes, grab a copy of our global variables and convert them
        into a coalesed data packet for the Display. We also control scene switching here and which scene to display.
        Outputs three dicts, `idle_stats`, `idle_stats_2, and `active_stats`.
        `idle_stats` = {'Flybys', 'Track', 'Range'}
        `idle_stats_2` = {'SunriseSunset', 'ReceiverStats'}
        `active_stats` = {'Callsign', 'Origin', 'Destination', 'FlightTime',
                          'Altitude', 'Speed', 'Distance', 'Country',
                          'Latitude', 'Longitude', 'Track', 'VertSpeed', 'RSSI'}
                       or {}.
        All values are formatted as strings. """
        global idle_data, idle_data_2, active_data, active_plane_display
        global ENHANCED_READOUT
        displayfeeder_start = time.perf_counter()
        filler_text = "---"

        def track_arrow(trk: int | float) -> str:
            """ Same routine as `main_loop_generator.relative_direction()`, just spits out arrows this time.
            (This runs under the assumption we're using the `fonts.smallest` or `fonts.microscopic` fonts;
            don't use with other fonts!) """
            dirs = ['▲', '◥', '▶', '◢', '▼', '◣', '◀', '◤']
            ix = round(trk / (360. / len(dirs)))
            return dirs[ix % len(dirs)]

        if active_data: # check if active_data exists and do a comparison after we're done
            active_data_i = True
        else:
            active_data_i = False

        # idle_stats
        total_flybys = "0"
        total_planes = "0"
        current_range = "0"
        if general_stats: # should always exist but just in case
            if rlat is not None and rlon is not None:
                if len(unique_planes_seen) >= 0 and len(unique_planes_seen) <= 9999:
                    total_flybys = f"{len(unique_planes_seen)}"
                elif len(unique_planes_seen) > 9999:
                    total_flybys = "9999"
                else: total_flybys = "0"
            else:
                total_flybys = "N/A"
            
            if DUMP1090_IS_AVAILABLE:
                if general_stats['Tracking'] > 999:
                    total_planes = ">999"
                else:
                    total_planes = f"{general_stats['Tracking']}"
            else:
                total_planes = "N/A"

            if DUMP1090_IS_AVAILABLE and (rlat is not None and rlon is not None):
                if general_stats['Range'] >= 999.5:
                    current_range = ">999"
                elif general_stats['Range'] >= 99.5 and general_stats['Range'] < 999.5: # just get us the integer values
                    current_range = f"{general_stats['Range']:.0f}"
                elif general_stats['Range'] >=9.95 and general_stats['Range'] < 99.5:
                    current_range = f"{general_stats['Range']:.1f}"
                elif general_stats['Range'] > 0 and general_stats['Range'] < 9.95:
                    current_range = f"{general_stats['Range']:.2f}"
                elif general_stats['Range'] == 0:
                    current_range = "0"
            else:
                current_range = "N/A"

        idle_stats = {
            'Flybys': total_flybys,
            'Track': total_planes,
            'Range': current_range,
        }

        # idle_stats_2 (clock center row)
        sunrise = ""
        sunset = ""
        receiver_string = ""
        rise_set = []
        recv_str = []
        if sunset_sunrise['Sunrise'] is not None and sunset_sunrise['Sunset'] is not None:
            if CLOCK_24HR:
                sunrise = sunset_sunrise['Sunrise'].strftime("%H:%M")
                sunset = sunset_sunrise['Sunset'].strftime("%H:%M")
            else:
                sunrise_1 = sunset_sunrise['Sunrise'].strftime("%I:%M%p")
                sunset_1 = sunset_sunrise['Sunset'].strftime("%I:%M%p")
                # end goal example: 06:00AM -> 6:00a
                if sunrise_1.startswith("0"):
                    sunrise = sunrise_1[1:-2] + sunrise_1[-2].lower()
                else:
                    sunrise = sunrise_1[:-2] + sunrise_1[-2].lower()
                if sunset_1.startswith("0"):
                    sunset = sunset_1[1:-2] + sunset_1[-2].lower()
                else:  
                    sunset = sunset_1[:-2] + sunset_1[-2].lower()
        else:
            sunrise = "--:--"
            sunset = "--:--"

        rise_set.append("▲")
        rise_set.append(sunrise)
        rise_set.append(" ")
        rise_set.append("▼")
        rise_set.append(sunset)
        
        # first section of receiver stats
        # "G____"
        recv_str.append("G")
        if receiver_stats['Gain'] is not None:
            recv_str.append(f"{receiver_stats['Gain']}".rjust(4))
        else:
            recv_str.append(filler_text.rjust(4))
        recv_str.append(" ")
        # second section of receiver stats
        # "N____"
        recv_str.append("N")
        if receiver_stats['Noise'] is not None:
            recv_str.append(f"{abs(receiver_stats['Noise'])}".rjust(4))
        else:
            recv_str.append(filler_text.rjust(4))
        recv_str.append(" ")
        # third section of receiver stats
        # "L__%" or "L---"
        recv_str.append("L")
        if receiver_stats['Strong'] is not None:
            strong_rounded = int(round(receiver_stats['Strong'], 0))
            if strong_rounded >= 100:
                recv_str.append("99%") # cap at 99%
            else:
                recv_str.append(f"{strong_rounded}".rjust(2))
                recv_str.append("%")
        else:
            recv_str.append(filler_text)
        receiver_string = "".join(recv_str)

        idle_stats_2 = {
            'SunriseSunset': "".join(rise_set),
            'ReceiverStats': receiver_string
            }

        # active_stats
        active_stats = {}
        if focus_plane and focus_plane_stats:
            flight_name = f"{focus_plane_stats['Flight']}"
            if focus_plane == FOLLOW_THIS_AIRCRAFT:
                flight_name = flight_name + "*"
            # flight name readout is limited to 8 characters
            if len(flight_name) > 8: flight_name = flight_name[:8]
            iso = f"{focus_plane_stats['Country']}"
            # speed readout is limited to 4 characters;
            # if speed >= 100, truncate to just the integers
            if focus_plane_stats['Speed'] >= 99.5 or focus_plane_stats['Speed'] == 0:
                gs = f"{focus_plane_stats['Speed']:.0f}"
            elif focus_plane_stats['Speed'] > 0 and focus_plane_stats['Speed'] < 99.5:
                gs = f"{focus_plane_stats['Speed']:.1f}"
            else:
                gs = "0"
            alt = f"{focus_plane_stats['Altitude']:.0f}"
            # distance readout is limited to 5 characters (2 direction, 3 value);
            # if distance >= 10, just get us the integers
            if rlat is not None and rlon is not None:
                if focus_plane_stats['Distance'] >= 0 and focus_plane_stats['Distance'] < 9.95:
                    dist = f"{focus_plane_stats['Distance']:.1f}"
                elif focus_plane_stats['Distance'] >= 9.95 and focus_plane_stats['Distance'] < 99.5:
                    dist = f"{focus_plane_stats['Distance']:.0f}"
                elif focus_plane_stats['Distance'] >= 99.5 and focus_plane_stats['Distance'] < 999.5:
                    dist = f"{focus_plane_stats['Distance']:.0f}"
                elif focus_plane_stats['Distance'] >= 999.5:
                    dist = "999"
                else: dist = "0"
                distance = focus_plane_stats['Direction'] + dist
            else:
                distance = "-----"
            # do our coordinate formatting
            lat_i = focus_plane_stats['Latitude']
            lon_i = focus_plane_stats['Longitude']
            if lat_i >= 0: lat_str = "N"
            elif lat_i <0: lat_str = "S"
            if lon_i >= 0: lon_str = "E"
            elif lon_i <0: lon_str = "W"
            lat = "{0:.3f}".format(abs(lat_i)) + lat_str
            lon = "{0:.3f}".format(abs(lon_i)) + lon_str
            # track indicator
            trkstr = ['T']
            trkstr.append(track_arrow(focus_plane_stats['Track']))
            trkstr.append(f"{focus_plane_stats['Track']:.0f}")
            trkstr.append("°")
            track = "".join(trkstr)
            # vertical speed is an interesting one; we are limited to 6 characters:
            # 1 for indicator, 1 for sign, and 4 for values
            vs_i = int(round(focus_plane_stats['VertSpeed'], 0))
            vs_str = f"{vs_i}"
            if abs(vs_i) >= 10000:
                vs_str = f"{(vs_i / 1000):.1f}"
            if vs_i > 0:
                vs_str = "+" + vs_str
            elif vs_i == 0:
                vs_str = " " + vs_str
            vs = "V" + vs_str
            rssi = f"{focus_plane_stats['RSSI']}"

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
                'Latitude': lat,
                'Longitude': lon,
                'Track': track,
                'VertSpeed': vs,
                'RSSI': rssi,
            }
        with threading.Lock():
            if not NOFILTER_MODE:
                if active_stats: active_plane_display = True
                else: active_plane_display = False
            else:
                active_plane_display = False

            if (active_stats == {}) != active_data_i:
                dispatcher.send(message='', signal=DISPLAY_SWITCH, sender=DisplayFeeder.data_packet) # as of now this isn't in use

            idle_data = idle_stats
            active_data = active_stats
            idle_data_2 = idle_stats_2
            process_time2[1] = round((time.perf_counter() - displayfeeder_start) * 1000, 3)

            # special handling for when we are tracking a specific aircraft under FOLLOW_THIS_AIRCRAFT
            if focus_plane_stats and focus_plane_stats['ID'] == FOLLOW_THIS_AIRCRAFT:
                if focus_plane_stats['Altitude'] < HEIGHT_LIMIT and focus_plane_stats['Distance'] < RANGE\
                   and not API_daily_limit_reached:
                    ENHANCED_READOUT = ENHANCED_READOUT_INIT
                else:
                    ENHANCED_READOUT = True
            else:
                if API_KEY and not API_daily_limit_reached and not ENHANCED_READOUT_INIT: # conditions when ENHANCED_READOUT should be False
                    ENHANCED_READOUT = False
                else:
                    ENHANCED_READOUT = ENHANCED_READOUT_INIT
    
    def run_loop(self):
        def keep_alive():
            self.loop.call_later(1, keep_alive)
        keep_alive()
        self.loop.run_forever()

    def end_thread(self, message):
        self.loop.stop()

class dump1090Watchdog:
    """ Monitors if dump1090 data is available while the main loop of FlightGazer is running.
    If the amount of `dump1090_failures` exceeds `dump1090_failures_to_watchdog_trigger`
    this 'watchdog' will get kicked and will suspend reading dump1090 for a set amount of time.
    """
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        register_signal_handler(self.loop, self.watchdog, signal=KICK_DUMP1090_WATCHDOG, sender=main_loop_generator)
        register_signal_handler(self.loop, self.end_thread, signal=END_THREADS, sender=sigterm_handler)
        self.run_loop()

    def watchdog(self, message):
        global DUMP1090_IS_AVAILABLE, relevant_planes, watchdog_triggers
        DUMP1090_IS_AVAILABLE = False
        with threading.Lock(): # indirectly let the other threads know that dump1090 is not available
            relevant_planes.clear()
        watchdog_triggers += 1
        if watchdog_triggers > (watchdog_setpoint - 1):
            main_logger.error(f"{dump1090} watchdog has been triggered too many times ({watchdog_setpoint}).")
            main_logger.error(">>> Permanently disabling dump1090 readout for this session.")
            main_logger.error(f"If this is a remote {dump1090} connection, please check your internet connectivity.")
            main_logger.error(f"If {dump1090} is running on this machine, please check the {dump1090} service.")
            main_logger.error(f"Please correct the underlying issue and restart FlightGazer.")
            return
        main_logger.error(f">>> Suspending checking {dump1090} for 10 minutes. This is occurrence: {watchdog_triggers}")
        time.sleep(600)
        main_logger.info(f"Re-enabling {dump1090} readout.")
        DUMP1090_IS_AVAILABLE = True

    def run_loop(self):
        def keep_alive():
            self.loop.call_later(1, keep_alive)
        keep_alive()
        self.loop.run_forever()

    def end_thread(self, message):
        self.loop.stop()

def brightness_controller() -> None:
    """ Changes desired display brightness based on current environment
    (ex: values of `ENABLE_TWO_BRIGHTNESS` or `sunset_sunrise`)
    Needs to run in its own thread. """
    global current_brightness
    if not ENABLE_TWO_BRIGHTNESS:
        main_logger.info("Dynamic brightness is disabled.")
        main_logger.info(f"Display will remain at a static brightness ({BRIGHTNESS}).")
        return
    
    if ACTIVE_PLANE_DISPLAY_BRIGHTNESS is not None:
        main_logger.info(f"Display will change to brightness level {ACTIVE_PLANE_DISPLAY_BRIGHTNESS} when an aircraft is detected.")

    try:
        switch_time1 = datetime.datetime.strptime(BRIGHTNESS_SWITCH_TIME['Sunrise'], "%H:%M").time()
        switch_time2 = datetime.datetime.strptime(BRIGHTNESS_SWITCH_TIME['Sunset'], "%H:%M").time()
        main_logger.info("Dynamic brightness is enabled.")
        main_logger.info(f"Display will change to brightness level {BRIGHTNESS} at sunrise and {BRIGHTNESS_2} at sunset.")
    except: # if BRIGHTNESS_SWITCH_TIME cannot be parsed, do not dynamically change brightness
        current_brightness = BRIGHTNESS
        main_logger.warning("Cound not parse BRIGHTNESS_SWITCH_TIME. This is required as a fallback.")
        main_logger.info(f">>> Display brightness will not dynamically change and will remain a static brightness. ({BRIGHTNESS})")
        return

    while True: # if the above tests pass, this thread can go to work
        current_time = datetime.datetime.now().astimezone()

        if (sunset_sunrise['Sunrise'] is None or sunset_sunrise['Sunset'] is None)\
            or not USE_SUNRISE_SUNSET:
            # note that depending on location and time of year, sunrise and sunset times can be None
            # thus we fall back on BRIGHNESS_SWITCH_TIME values (at this point the values have been known to work)
            sunrise_time = datetime.datetime.combine(current_time.date(), switch_time1).astimezone()
            sunset_time = datetime.datetime.combine(current_time.date(), switch_time2).astimezone()
        else:
            sunrise_time = sunset_sunrise['Sunrise']
            sunset_time = sunset_sunrise['Sunset']

        if ACTIVE_PLANE_DISPLAY_BRIGHTNESS is not None and active_plane_display:
            # current_brightness = ACTIVE_PLANE_DISPLAY_BRIGHTNESS
            pass # let the display driver handle the brightness in this scenario
        else:
            if current_time > sunrise_time and current_time < sunset_time:
                current_brightness = BRIGHTNESS
            else:
                current_brightness = BRIGHTNESS_2

        time.sleep(1)

def display_FPS_counter(display_instance) -> None:
    """ Poll the performance of the display animator (and other attributes). (Needs to run in its own thread) """
    def write_out() -> None:
        global process_time, display_fps, display_failures
        process_time[3] = render_time[0]
        display_fps = render_time[1]
        display_failures = broken_display_count

    while True:
        render_time = [0.0, 0.0]
        broken_display_count = display_failures

        if DISPLAY_IS_VALID: # recall: this can change if the display driver breaks
            try:
                render_time = display_instance.render_time
                broken_display_count = display_instance.itbroke_count
            except AttributeError:
                write_out()
                return
        else:
            write_out()
            return
        
        write_out()
        time.sleep(1)

def export_FlightGazer_state() -> None:
    """ Write to a json in `/run/FlightGazer` every `LOOP_INTERVAL` that dumps almost
    all the values stored in the globals. Essentially what `print_to_console()` does but now
    accessible outside of FlightGazer. Could be useful for other programs. (needs to run in its own thread) """
    global process_time2
    stats_dir = Path("/run/FlightGazer")
    json_file = Path(f"{stats_dir}/current_state.json")
    if not os.name == 'posix' or not Path('/run').exists():
        main_logger.info("FlightGazer state will not be written. (Not running on Linux or /run does not exist.)")
        return
    if not stats_dir.exists():
        try:
            stats_dir.mkdir(parents=True, exist_ok=True)
            main_logger.debug(f"Creating directory {stats_dir} for FlightGazer state.")
        except:
            main_logger.warning(f"Could not create directory {stats_dir} for FlightGazer state.")
            return
    if not json_file.exists():
        try:
            json_file.touch(exist_ok=True)
        except:
            main_logger.warning(f"Could not create file {json_file} for FlightGazer state.")
            return
    
    while True:
        try:
            export_start = time.perf_counter()
            time_now = datetime.datetime.now()
            FlightGazer = {
                'start_date': STARTED_DATE.strftime("%Y-%m-%dT%H:%M:%S"),
                'start_time': START_TIME,
                'runtime': timedelta_clean(time.monotonic() - START_TIME),
                'version': VERSION,
                'config_version': config_version,
                'refresh_rate': LOOP_INTERVAL,
                'distance_unit': distance_unit,
                'speed_unit': speed_unit,
                'altitude_unit': altitude_unit,
                'clock_24hr': CLOCK_24HR,
                'sunrise_and_sunset': [idle_data_2['SunriseSunset'].split(" ")[0][1:],
                                       idle_data_2['SunriseSunset'].split(" ")[1][1:]] if
                                       idle_data_2['SunriseSunset'] else None,
                'filter_settings': {
                    'range_limit': RANGE,
                    'height_limit': HEIGHT_LIMIT,
                    'follow_this_aircraft': FOLLOW_THIS_AIRCRAFT if FOLLOW_THIS_AIRCRAFT else None,
                    'location_timeout_sec': LOCATION_TIMEOUT,
                    'flyby_staleness_min': FLYBY_STALENESS,
                },
            }
            receivers = {
                'dump1090_is_available': DUMP1090_IS_AVAILABLE,
                'dump1090_json': DUMP1090_JSON,
                'dump978_json': DUMP978_JSON,
                'using_filesystem': USING_FILESYSTEM,
                'using_filesystem_978': USING_FILESYSTEM_978,
                'dump1090_type': dump1090 if DUMP1090_JSON is not None else None,
                'location_is_set': True if (rlat is not None and rlon is not None) else False,
                'response_time_ms': process_time[0],
                'json_size_KiB': round(runtime_sizes[0] / 1024, 3),
                'json_transfer_rate_MiB_per_sec': 0. if process_time[0] == 0 else
                                    round((runtime_sizes[0] * 1000)/(process_time[0] * 1048576), 3),
                'json_processing_time_ms': process_time2[2],
                'json_processing_rate_MiB_per_sec': 0. if process_time2[2] == 0 else
                                    round((runtime_sizes[0] * 1000)/(process_time2[2] * 1048576), 3),
                'filtering_and_algorithm_time_ms': process_time[1],
                'receiver_stats': receiver_stats,
            }

            plane_stats = {
                'currently_tracking': general_stats['Tracking'] if general_stats else 0,
                'current_range': general_stats['Range'] if general_stats else 0,
                'flybys_today': len(unique_planes_seen),
                'last_unique_plane': unique_planes_seen[-1] if unique_planes_seen else None,
                'aircraft_selections': selection_events,
                'rare_selection_events': algorithm_rare_events,
                'no_filter': NOFILTER_MODE,
                'focus_plane_iter': focus_plane_iter,
                'focus_plane_ids_discard': list(focus_plane_ids_discard),
                'focus_plane_ids_scratch': list(focus_plane_ids_scratch),
                'focus_plane': focus_plane if focus_plane else None,
                'in_range': len(relevant_planes),
                'relevant_planes': relevant_planes,
            }

            api_stats = {
                'api_enabled': True if API_KEY else False,
                'api_key': f"*****{API_KEY[-5:]}" if API_KEY else None,
                'successful_calls': api_hits[0],
                'failed_calls': api_hits[1],
                'calls_with_no_data': api_hits[2],
                'cache_hits': api_hits[3],
                'baseline_use': api_usage_cost_baseline,
                'cost_today': estimated_api_cost,
                'estimated_use': api_usage_cost_baseline + estimated_api_cost,
                'api_cost_limit_reached': API_cost_limit_reached,
                'api_daily_limit_reached': API_daily_limit_reached,
                'last_api_response_time_ms': process_time[2],
                'last_api_result': focus_plane_api_results[-1],
            }

            display_status = {
                'no_display_mode': NODISPLAY_MODE,
                'display_is_valid': DISPLAY_IS_VALID,
                'driver': None if not DISPLAY_IS_VALID else ('rgbmatrix' if not EMULATE_DISPLAY else 'RGBMatrixEmulator'),
                'current_mode': None if not DISPLAY_IS_VALID else ('active (plane display)' if active_plane_display else 'idle (clock)'),
                'journey_plus_enabled': JOURNEY_PLUS,
                'enhanced_readout_enabled': ENHANCED_READOUT,
                'enhanced_readout_fallback_running': True if (ENHANCED_READOUT != ENHANCED_READOUT_INIT) else False,
                'display_formatting_time_ms': process_time2[1],
                'fps': display_fps,
                'render_time_ms': process_time[3],
                'current_brightness': (ACTIVE_PLANE_DISPLAY_BRIGHTNESS if 
                                      (active_plane_display and ACTIVE_PLANE_DISPLAY_BRIGHTNESS is not None)
                                      else current_brightness 
                                      ) if DISPLAY_IS_VALID else None,
            }

            runtime_status = {
                'interactive_mode': INTERACTIVE,
                'last_console_print_time_ms': process_time2[0],
                'last_json_export_time_ms': process_time2[3],
                'verbose_mode': VERBOSE_MODE,
                'inside_tmux': INSIDE_TMUX,
                'flyby_stats_present': flyby_stats_present,
                'watchdog_triggered': True if (not DUMP1090_IS_AVAILABLE and watchdog_triggers > 0) else False,
                'dump1090_failures': dump1090_failures,
                'watchdog_triggers': watchdog_triggers,
                'display_failures': None if NODISPLAY_MODE else display_failures,
                'cpu_percent': round(this_process_cpu / CORE_COUNT, 3),
                'cpu_temp_C': round(psutil.sensors_temperatures()[CPU_TEMP_SENSOR][0].current, 1) if CPU_TEMP_SENSOR else None,
                'memory_MiB': round(psutil.Process().memory_info().rss / 1048576, 3),
                'pid': this_process.pid,
            }

            output = {
                'time_now': time_now.strftime("%Y-%m-%dT%H:%M:%S"),
                'FlightGazer': FlightGazer,
                'receivers': receivers,
                'plane_stats': plane_stats,
                'api_stats': api_stats,
                'display_status': display_status,
                'runtime_status': runtime_status,
            }

            with open(json_file, 'w') as f:
                if ORJSON_IMPORTED:
                    f.write(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())
                else:
                    f.write(json.dumps(output)) # no indentation, it's like 50x slower than orjson (from the orjson docs)
            process_time2[3] = round((time.perf_counter() - export_start) * 1000, 3)

        except Exception as e:
            main_logger.error(f"Could not write to {json_file}. Error: {e}", exc_info=True)
            main_logger.error("Writing state to json has stopped.")
            return

        time.sleep(LOOP_INTERVAL)

# ========== Display Superclass ============
# ==========================================

class Display(
    Animator
):
    """ Our Display driver. """
    """ Programmer's notes:
    Uses techniques from Colin Waddell's its-a-plane-python project but diverges significantly from his design.

    This Display class is a huge mess, but it works and its structure has not changed since v.0.8.0.
    Why is this class not broken out as its own module? Threading and global variables, basically. A rewrite at this point isn't worth it imho.
    Data to display is handled and parsed by `DisplayFeeder` while time-based elements like the clock are handled internally.
    Actual draw routines and shape primitives are also handled internally.
    The actual workings of this class should already be well-explained with all the comments and docstrings.

    Use the @Animator decorator to control both how often elements update along with associated logic evaluations.
    When using the decorator, the second (optional) argument specifies the offset for each element in the render queue such that
    when (global frame counter - offset) % frame duration == 0, the function will run (except for the first frame).
    Additional quirks: functions when requested to render on the same frame as another are rendered alphabetically, not
    in the order they are defined in the class. Hence why functions within this class will have a letter prefix before their name.
    Additionally, each function has their own internal frame counter `count` for each time they are run, incremented by `Animator`.
    If a function returns True, this resets that internal counter.

    Frame ---->  0      1      2      3      4 ...
    a_func(1)    ░░░0░░░▒▒▒1▒▒▒░░░2░░░▒▒▒3▒▒▒
    ab_func(2,1) ░░░░░░░0░░░░░░▒▒▒▒▒▒▒1▒▒▒▒▒▒
    b_func(1)    ░░░0░░░▒▒▒1▒▒▒░░░2░░░▒▒▒3▒▒▒
    c_func(3,1)         ░░░░░░░░░░0░░░░░░░░░░
    ...
    """
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
        # idle stats 2 (clock center row)
        self._last_row1_data = None
        self._last_row2_data = None
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
        self._last_latitude = None
        self._last_longitude = None
        self._last_groundtrack = None
        self._last_vertspeed = None
        self._last_rssi = None
        self._last_switch_progress_bar = None
        self._last_journey_plus_row = None
        # brightness control
        self._last_brightness = self.matrix.brightness
        # blinker variables for callsign (see `callsign_blinker()`)
        self._callsign_is_blanked = False
        self._callsign_blinker_cache = None
        self._callsign_blinker_cache_last = None
        self._callsign_frame_decrement = None
        # switch between ENHANCED_READOUT and normal readout
        self._enhanced_readout_last = ENHANCED_READOUT_INIT

        # Initialize animator
        super().__init__()

        # Overwrite any default settings from Animator
        self.delay = frames.PERIOD

        # Error control: count how many times something broke in here
        self.itbroke_count = 0

    # Control display "responsiveness" (how often each function should update, in frames)
    refresh_speed = math.ceil(frames.PER_SECOND * 0.1)

    def draw_square(self, x0:int, y0:int, x1:int, y1:int, color):
        for x in range(x0, x1):
            _ = graphics.DrawLine(self.canvas, x, y0, x, y1, color)

    @Animator.KeyFrame.add(0)
    def a_clear_screen(self):
        # First operation after a screen reset
        self.canvas.Clear()

    """ Watches when we need to switch to active plane display or if ENHANCED_READOUT changes """
    @Animator.KeyFrame.add(1)
    def aa_scene_switch(self, count):
        if self._last_active_state != active_plane_display:
            self.active_plane_display = active_plane_display
            self.reset_scene()
        self._last_active_state = self.active_plane_display
        # in case this switches
        if self._enhanced_readout_last != ENHANCED_READOUT:
            self.reset_scene()
        self._enhanced_readout_last = ENHANCED_READOUT
        return True

    """ Blink the callsign upon plane change or if active plane display starts """
    @Animator.KeyFrame.add(1)
    def b_callsign_blinker(self, count):
        half_cycle_time: float = 0.5 # in seconds
        frame_count_per_sec = frames.PER_SECOND
        switch_after_these_many_frames = int(round(frame_count_per_sec * half_cycle_time, 0))
        times_to_blink: int = 5
        # (times_to_blink * 2) gives us a full cycle in regards to frames
        frame_decrement_init = int(switch_after_these_many_frames * (times_to_blink * 2))

        def reinit():
            self._callsign_frame_decrement = frame_decrement_init
            self._callsign_is_blanked = False

        if self._callsign_frame_decrement is None or\
            (not self.active_plane_display or not focus_plane):
            # reset the decrementer if we haven't initialized it yet or plane display is off 
            reinit()
            self._callsign_blinker_cache_last = None
            return True
        self._callsign_blinker_cache = focus_plane_stats['ID'] # get current hex ID at this loop
        # if the callsign changed after we're done blinking (decrement == 0) and active plane display is still true
        if self._callsign_blinker_cache_last is not None and\
            self._callsign_blinker_cache_last != self._callsign_blinker_cache:
            reinit()
        if self._callsign_frame_decrement == 0: # stop the blinking
            self._callsign_is_blanked = False
            return True
        if self._callsign_frame_decrement % switch_after_these_many_frames == 0:
            self._callsign_is_blanked = not self._callsign_is_blanked # the actual "blink"
        self._callsign_frame_decrement -= 1
        self._callsign_blinker_cache_last = self._callsign_blinker_cache # move this loop's cache to another cache to check at a later time

    # =========== Clock Elements =============
    # ========================================

    """ Seconds """
    @Animator.KeyFrame.add(refresh_speed)
    def c_second(self, count):
        if self.active_plane_display:
            self._last_seconds = None
            return True
        SECONDS_FONT = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
        SECONDS_POSITION = (41, 12)
        SECONDS_COLOR = colors.seconds_color

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
            return True

    """ Hour and minute """
    @Animator.KeyFrame.add(refresh_speed)
    def d_clock(self, count):
        if self.active_plane_display:
            self._last_time = None
            return True
        CLOCK_FONT = fonts.large_bold
        CLOCK_POSITION = (1, 12)
        CLOCK_COLOR = colors.clock_color

        now = datetime.datetime.now()
        if not CLOCK_24HR:
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
            return True

    """ AM/PM Indicator """
    @Animator.KeyFrame.add(refresh_speed)
    def e_ampm(self, count):
        if self.active_plane_display or CLOCK_24HR:
            self._last_ampm = None
            return True
        AMPM_COLOR = colors.am_pm_color
        AMPM_FONT = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
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
            return True
    
    """ Day of the week """
    @Animator.KeyFrame.add(refresh_speed)
    def f_day(self, count):
        if self.active_plane_display:
            self._last_day = None
            return True
        DAY_COLOR = colors.day_of_week_color
        DAY_FONT = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
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
            return True

    """ Date """
    @Animator.KeyFrame.add(refresh_speed)
    def g_date(self, count):
        if self.active_plane_display:
            self._last_date = None
            return True
        DATE_COLOR = colors.date_color
        DATE_FONT = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
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
            return True
    
    # ========= Idle Stats Elements ==========
    # ========================================
    """ Static text """
    @Animator.KeyFrame.add(refresh_speed)
    def h_idle_header(self, count):
        if self.active_plane_display: return True
        small_font_style = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
        HEADER_TEXT_FONT = small_font_style if not CLOCK_CENTER_ROW_2ROWS else fonts.microscopic
        FLYBY_HEADING_COLOR = colors.flyby_header_color
        TRACK_HEADING_COLOR = colors.track_header_color
        RANGE_HEADING_COLOR = colors.range_header_color
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
    @Animator.KeyFrame.add(refresh_speed)
    def i_stats_readout(self, count):
        if self.active_plane_display:
            self._last_flybys = None
            self._last_track = None
            self._last_range = None
            return True
        STATS_TEXT_FONT = fonts.small
        FLYBY_TEXT_COLOR = colors.flyby_color
        TRACK_TEXT_COLOR = colors.track_color
        RANGE_TEXT_COLOR = colors.range_color
        READOUT_TEXT_Y = 31
        FLYBY_X_POS = 1
        TRACK_X_POS = 24
        RANGE_X_POS = 45
        return_flag = False

        flybys_now = idle_data.get('Flybys', "N/A")
        tracking_now = idle_data.get('Track', "N/A")
        range_now = idle_data.get('Range', "N/A")

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

            self._last_flybys = flybys_now

            _ = graphics.DrawText(
                self.canvas,
                STATS_TEXT_FONT,
                FLYBY_X_POS,
                READOUT_TEXT_Y,
                FLYBY_TEXT_COLOR,
                flybys_now,
            )
            return_flag = True

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

            self._last_track = tracking_now

            _ = graphics.DrawText(
                self.canvas,
                STATS_TEXT_FONT,
                TRACK_X_POS,
                READOUT_TEXT_Y,
                TRACK_TEXT_COLOR,
                tracking_now,
            )
            return_flag = True

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

            self._last_range = range_now

            _ = graphics.DrawText(
                self.canvas,
                STATS_TEXT_FONT,
                RANGE_X_POS,
                READOUT_TEXT_Y,
                RANGE_TEXT_COLOR,
                range_now,
            )
            return_flag = True

        return return_flag
    
    """ Idle Stats 2: Clock center row """
    @Animator.KeyFrame.add(refresh_speed)
    def j_idle_stats_2(self, count):
        if self.active_plane_display or not CLOCK_CENTER_ENABLED:
            self._last_row1_data = None
            self._last_row2_data = None
            return True
        return_flag = False
        
        def center_align(text_len:int) -> int:
            """ Center aligns text based on its length across the screen """
            if text_len >= 16:
                return 1
            elif text_len == 0 or text_len == 1:
                return 31
            else:
                # font is monospaced and each glyph is 4 pixels wide
                return (30 - ((text_len - 1) * 2))
        
        small_font_style = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
        ROW1_FONT = small_font_style if not CLOCK_CENTER_ROW_2ROWS else fonts.microscopic
        ROW_2_FONT = fonts.microscopic
        ROW1_COLOR = colors.center_row1_color
        ROW2_COLOR = colors.center_row2_color
        ROW1_Y = 18 if not CLOCK_CENTER_ROW_2ROWS else 16
        ROW2_Y = 20

        sunrise_sunset_now = idle_data_2.get('SunriseSunset', "▲--:-- ▼--:--")
        receiver_stats_now = idle_data_2.get('ReceiverStats', "G --- N --- L--")
        calendar_info_now = datetime.datetime.now().strftime('%b WK%V D%j').upper() if CLOCK_CENTER_ROW_2ROWS else\
                            datetime.datetime.now().strftime('%b wk%V d%j')
        
        # row 1 data
        if CLOCK_CENTER_ROW['ROW1'] is None:
            row1_data = ""
        elif CLOCK_CENTER_ROW['ROW1'] == 1:
            row1_data = sunrise_sunset_now
        elif CLOCK_CENTER_ROW['ROW1'] == 2:
            row1_data = receiver_stats_now
        elif CLOCK_CENTER_ROW['ROW1'] == 3:
            row1_data = calendar_info_now
        # row 2 data
        if CLOCK_CENTER_ROW['ROW2'] is None:
            row2_data = ""
        elif CLOCK_CENTER_ROW['ROW2'] == 1:
            row2_data = sunrise_sunset_now
        elif CLOCK_CENTER_ROW['ROW2'] == 2:
            row2_data = receiver_stats_now
        elif CLOCK_CENTER_ROW['ROW2'] == 3:
            row2_data = calendar_info_now

        if self._last_row1_data != row1_data:
            if self._last_row1_data is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    ROW1_FONT,
                    center_align(len(self._last_row1_data)),
                    ROW1_Y,
                    colors.BLACK,
                    self._last_row1_data,
                )
            self._last_row1_data = row1_data

            _ = graphics.DrawText(
                self.canvas,
                ROW1_FONT,
                center_align(len(row1_data)),
                ROW1_Y,
                ROW1_COLOR,
                row1_data,
            )
            return_flag = True

        if CLOCK_CENTER_ROW_2ROWS:
            if self._last_row2_data != row2_data:
                if self._last_row2_data is not None:
                    _ = graphics.DrawText(
                        self.canvas,
                        ROW_2_FONT,
                        center_align(len(self._last_row2_data)),
                        ROW2_Y,
                        colors.BLACK,
                        self._last_row2_data,
                    )
                self._last_row2_data = row2_data

                _ = graphics.DrawText(
                    self.canvas,
                    ROW_2_FONT,
                    center_align(len(row2_data)),
                    ROW2_Y,
                    ROW2_COLOR,
                    row2_data,
                )
                return_flag = True

        return return_flag

    # ======== Active Plane Readout ==========
    # ========================================
    """ Header information: Callsign, Distance, Country """
    @Animator.KeyFrame.add(refresh_speed)
    def k_top_header(self, count):
        if not self.active_plane_display:
            self._last_callsign = None
            self._last_distance = None
            self._last_country = None
            return True
        TOP_HEADER_FONT = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
        CALLSIGN_COLOR = colors.callsign_color
        DISTANCE_COLOR = colors.distance_color
        COUNTRY_COLOR = colors.country_color
        BASELINE_Y = 6
        CALLSIGN_X_POS = 1
        DISTANCE_X_POS = 35
        COUNTRY_X_POS = 56
        return_flag = False

        # we want to blink this text
        if not self._callsign_is_blanked:
            callsign_now = active_data.get('Callsign', "")
        else:
            callsign_now = ""
        distance_now = active_data.get('Distance', "  N/A")
        country_now = active_data.get('Country', "??")

        if self._last_callsign != callsign_now:
            if self._last_callsign is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.smallest_alt,
                    CALLSIGN_X_POS,
                    BASELINE_Y,
                    colors.BLACK,
                    self._last_callsign
                )
            self._last_callsign = callsign_now

            _ = graphics.DrawText(
                self.canvas,
                fonts.smallest_alt,
                CALLSIGN_X_POS,
                BASELINE_Y,
                CALLSIGN_COLOR,
                callsign_now
            )
            return_flag = True

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
            self._last_distance = distance_now
    
            _ = graphics.DrawText(
                self.canvas,
                TOP_HEADER_FONT,
                DISTANCE_X_POS,
                BASELINE_Y,
                DISTANCE_COLOR,
                distance_now
            )
            return_flag = True

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
            self._last_country = country_now

            _ = graphics.DrawText(
                self.canvas,
                TOP_HEADER_FONT,
                COUNTRY_X_POS,
                BASELINE_Y,
                COUNTRY_COLOR,
                country_now
            )
            return_flag = True

        return return_flag

    """ Our journey indicator (origin and destination) """
    @Animator.KeyFrame.add(refresh_speed)
    def l_journey(self, count):
        if not self.active_plane_display or ENHANCED_READOUT:
            self._last_origin = None
            self._last_destination = None
            return True
        return_flag = False

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

        # array of constants, depending on if `JOURNEY_PLUS` is enabled
        if not JOURNEY_PLUS:
            CONSTANTS = {'y_baseline': 18,
                         'origin_x_pos': 3,
                         'destination_x_pos': 37,
                         'arrow_x': 33,
                         'arrow_y': 13,
                         'arrow_w': 4,
                         'arrow_h': 8,
                         'bbox_x_start': 0,
                         'bbox_x_end': 62,
                         'bbox_y_height': 10}
        else:
            CONSTANTS = {'y_baseline': 16,
                         'origin_x_pos': 1,
                         'destination_x_pos': 24,
                         'arrow_x': 22,
                         'arrow_y': 11,
                         'arrow_w': 3,
                         'arrow_h': 7,
                         'bbox_x_start': 0,
                         'bbox_x_end': 41,
                         'bbox_y_height': 9}

        JOURNEY_Y_BASELINE = CONSTANTS['y_baseline']
        ORIGIN_X_POS = CONSTANTS['origin_x_pos']
        DESTINATION_X_POS = CONSTANTS['destination_x_pos']
        ORIGIN_COLOR = colors.origin_color
        DESTINATION_COLOR = colors.destination_color
        ARROW_COLOR = colors.arrow_color

        origin_now = active_data.get('Origin', "---")
        destination_now = active_data.get('Destination', "---")

        # Undraw method
        # Note this is different than the other methods as we just black out the area instead
        # of undrawing the text. Additionally, we just continually draw to the canvas
        # every time this function is run because it's simpler that way
        if self._last_origin != origin_now or self._last_destination != destination_now:
            if self._last_origin is not None or self._last_destination is not None:
                self.draw_square(
                    CONSTANTS['bbox_x_start'],
                    JOURNEY_Y_BASELINE - 1,
                    CONSTANTS['bbox_x_end'],
                    JOURNEY_Y_BASELINE - CONSTANTS['bbox_y_height'] - 1,
                    colors.BLACK
                )
            return_flag = True

        # store our current data for readout in the future
        self._last_origin = origin_now
        self._last_destination = destination_now

        # Draw our arrow
        journey_arrow(self.canvas,
                      CONSTANTS['arrow_x'],
                      CONSTANTS['arrow_y'],
                      CONSTANTS['arrow_w'],
                      CONSTANTS['arrow_h'],
                      ARROW_COLOR)
        
        if not JOURNEY_PLUS:
            # Draw origin; adjust font for all anticipated string lengths
            if len(origin_now) <= 3:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.large_bold,
                    ORIGIN_X_POS,
                    JOURNEY_Y_BASELINE,
                    ORIGIN_COLOR,
                    origin_now
                )
            elif len(origin_now) == 4:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.regularplus,
                    ORIGIN_X_POS,
                    JOURNEY_Y_BASELINE,
                    ORIGIN_COLOR,
                    origin_now
                )
            elif len(origin_now) > 4:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.small,
                    ORIGIN_X_POS,
                    JOURNEY_Y_BASELINE,
                    ORIGIN_COLOR,
                    origin_now
                )

            # Draw destination; do the same approach as above
            if len(destination_now) <= 3:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.large_bold,
                    DESTINATION_X_POS,
                    JOURNEY_Y_BASELINE,
                    DESTINATION_COLOR,
                    destination_now
                )
            elif len(destination_now) == 4:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.regularplus,
                    DESTINATION_X_POS,
                    JOURNEY_Y_BASELINE,
                    DESTINATION_COLOR,
                    destination_now
                )
            elif len(destination_now) > 4:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.small,
                    DESTINATION_X_POS,
                    JOURNEY_Y_BASELINE,
                    DESTINATION_COLOR,
                    destination_now
                )

        else:
            if len(origin_now) <= 3:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.regularplus,
                    ORIGIN_X_POS,
                    JOURNEY_Y_BASELINE,
                    ORIGIN_COLOR,
                    origin_now
                )
            elif len(origin_now) == 4:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest,
                    ORIGIN_X_POS + 2,
                    JOURNEY_Y_BASELINE - 2,
                    ORIGIN_COLOR,
                    origin_now
                )
            elif len(origin_now) > 4:
                # we are able to do some jank here because we don't have to deal
                # with the same kind of undraw routines used in other functions.
                # This is to handle the rare edge case when the API results give us
                # a coordinate instead of an IATA code, so we write text on two lines
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest,
                    ORIGIN_X_POS + 2,
                    JOURNEY_Y_BASELINE - 4,
                    ORIGIN_COLOR,
                    origin_now[:4]
                )
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest,
                    ORIGIN_X_POS + 2,
                    JOURNEY_Y_BASELINE + 1,
                    ORIGIN_COLOR,
                    origin_now[4:8]
                )

            if len(destination_now) <= 3:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.regularplus,
                    DESTINATION_X_POS,
                    JOURNEY_Y_BASELINE,
                    DESTINATION_COLOR,
                    destination_now
                )
            elif len(destination_now) == 4:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest,
                    DESTINATION_X_POS,
                    JOURNEY_Y_BASELINE - 2,
                    DESTINATION_COLOR,
                    destination_now
                )
            elif len(destination_now) > 4:
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest,
                    DESTINATION_X_POS,
                    JOURNEY_Y_BASELINE - 4,
                    DESTINATION_COLOR,
                    destination_now[:4]
                )
                _ = graphics.DrawText(
                    self.canvas,
                    fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest,
                    DESTINATION_X_POS,
                    JOURNEY_Y_BASELINE + 1,
                    DESTINATION_COLOR,
                    destination_now[4:8]
                )

        return return_flag

    """ Journey Plus: Relocate the flight time and add additional info like Enhanced Readout """
    @Animator.KeyFrame.add(refresh_speed)
    def ll_journeyplus(self, count): # Love Live?
        """ This function is different because we go against the adage that `DisplayFeeder` should be doing 
        most of the formatting work. Instead of having to add more functionality to it, we just
        reuse the results to enable functionality for JOURNEY_PLUS. """
        if not self.active_plane_display or not JOURNEY_PLUS or ENHANCED_READOUT:
            self._last_journey_plus_row = None
            return True
        return_flag = False

        TIME_HEADER_X = 47
        TIME_HEADER_Y = 10
        # TIME_READOUT_X controlled by a function that right-aligns it
        TIME_READOUT_Y = 16
        CENTER_READOUT_X = 2
        CENTER_READOUT_Y = 21
        TIME_READOUT_FONT = fonts.small
        CENTER_READOUT_FONT = fonts.extrasmall
        TIME_HEADER_COLOR = colors.time_header_color
        TIME_READOUT_COLOR = colors.time_readout_color
        CENTER_READOUT_COLOR = colors.center_readout_color

        def right_align(string: str) -> int:
            """ special case to align-right the time output """
            length_s = len(string)
            if length_s <= 3: return 48
            if length_s == 4: return 46
            elif length_s >= 5: return 41

        flighttime_now: str = active_data.get('FlightTime', '---')
        # undo the formatting done by `strfdelta()`
        # 0h00m -> 0:00
        if not flighttime_now.startswith("-"): # recall the filler text: "---"
            ft_split = flighttime_now.split('h')
            flighttime = []
            flighttime.append(ft_split[0])
            flighttime.append(":")
            flighttime.append(ft_split[1][:-1])
            flighttime_text = "".join(flighttime)
        else:
            flighttime_text = "---"

        groundtrack_now: str = active_data.get('Track', "T▲0°")
        vertspeed_now: str = active_data.get('VertSpeed', "V 0")
        center_row = []
        center_row.append(groundtrack_now.ljust(6))
        center_row.append(vertspeed_now.ljust(6))
        center_row_text = "".join(center_row)

        # time header, no need to update
        _ = graphics.DrawText(
            self.canvas,
            fonts.microscopic,
            TIME_HEADER_X,
            TIME_HEADER_Y,
            TIME_HEADER_COLOR,
            "TIME"
        )

        if flighttime_text != self._last_flighttime:
            if self._last_flighttime is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    TIME_READOUT_FONT,
                    right_align(self._last_flighttime),
                    TIME_READOUT_Y,
                    colors.BLACK,
                    self._last_flighttime
                )
            self._last_flighttime = flighttime_text

            _ = graphics.DrawText(
                self.canvas,
                TIME_READOUT_FONT,
                right_align(flighttime_text),
                TIME_READOUT_Y,
                TIME_READOUT_COLOR,
                flighttime_text
            )
            return_flag = True

        if center_row_text != self._last_journey_plus_row:
            if self._last_journey_plus_row is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    CENTER_READOUT_FONT,
                    CENTER_READOUT_X,
                    CENTER_READOUT_Y,
                    colors.BLACK,
                    self._last_journey_plus_row
                )
            self._last_journey_plus_row = center_row_text

            _ = graphics.DrawText(
                self.canvas,
                CENTER_READOUT_FONT,
                CENTER_READOUT_X,
                CENTER_READOUT_Y,
                CENTER_READOUT_COLOR,
                center_row_text
            )
            return_flag = True

        return return_flag

    """ Enhanced readout part 1: replace journey with latitude and longitude """
    @Animator.KeyFrame.add(refresh_speed)
    def m_lat_lon(self, count):
        if not self.active_plane_display or not ENHANCED_READOUT:
            self._last_latitude = None
            self._last_longitude = None
            return True
        X_POS = 1
        LAT_Y_POS = 12
        LON_Y_POS = 18
        LATITUDE_COLOR = colors.latitude_color
        LONGITUDE_COLOR = colors.longitude_color
        FONT = fonts.small
        return_flag = False

        lat_now = active_data.get('Latitude', "0.000N")
        lon_now = active_data.get('Longitude', "0.000E")
        
        # Undraw sections
        if self._last_latitude != lat_now:
            if self._last_latitude is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    FONT,
                    X_POS,
                    LAT_Y_POS,
                    colors.BLACK,
                    self._last_latitude
                )
            self._last_latitude = lat_now

            _ = graphics.DrawText(
                self.canvas,
                FONT,
                X_POS,
                LAT_Y_POS,
                LATITUDE_COLOR,
                lat_now
            )
            return_flag = True

        if self._last_longitude != lon_now:
            if self._last_longitude is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    FONT,
                    X_POS,
                    LON_Y_POS,
                    colors.BLACK,
                    self._last_longitude
                )
            self._last_longitude = lon_now
        
            _ = graphics.DrawText(
                self.canvas,
                FONT,
                X_POS,
                LON_Y_POS,
                LONGITUDE_COLOR,
                lon_now
            )
            return_flag = True

        return return_flag

    """ Static text """
    @Animator.KeyFrame.add(refresh_speed)
    def n_active_header(self, count):
        if not self.active_plane_display: return True
        if JOURNEY_PLUS and not ENHANCED_READOUT:
            HEADER_TEXT_FONT = fonts.microscopic
        else:
            HEADER_TEXT_FONT = fonts.small
        ALTITUDE_HEADING_COLOR = colors.altitude_heading_color
        SPEED_HEADING_COLOR = colors.speed_heading_color
        TIME_HEADING_COLOR = colors.time_rssi_heading_color
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
            24,
            ACTIVE_TEXT_Y,
            SPEED_HEADING_COLOR,
            "SPD"
        )
        if not JOURNEY_PLUS and not ENHANCED_READOUT:
            _ = graphics.DrawText(
                self.canvas,
                HEADER_TEXT_FONT,
                48,
                ACTIVE_TEXT_Y,
                TIME_HEADING_COLOR,
                "TIME"
            )
        else:
            _ = graphics.DrawText(
                self.canvas,
                HEADER_TEXT_FONT,
                48 if (JOURNEY_PLUS and not ENHANCED_READOUT) else 47,
                ACTIVE_TEXT_Y,
                TIME_HEADING_COLOR,
                "RSSI"
            )

    """ Our active stats readout """
    @Animator.KeyFrame.add(refresh_speed)
    def o_active_readout(self, count):
        if not self.active_plane_display:
            self._last_altitude = None
            self._last_speed = None
            self._last_flighttime = None
            return True
        STATS_TEXT_FONT = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
        ALTITUDE_TEXT_COLOR = colors.altitude_color
        SPEED_TEXT_COLOR = colors.speed_color
        TIME_TEXT_COLOR = colors.time_rssi_color
        READOUT_TEXT_Y = 31
        ALTITUDE_X_POS = 1
        SPEED_X_POS = 24
        # TIME_X_POS controlled by the below function
        return_flag = False

        def right_align(string: str) -> int:
            """ special case to align-right the time output """
            length_s = len(string)
            if length_s <= 4: return 48
            elif length_s == 5: return 44
            elif length_s >= 6: return 40
            
        altitude_now = active_data.get('Altitude', "0")
        speed_now = active_data.get('Speed', "0")
        flighttime_now = active_data.get('FlightTime', "---")
        rssi_now = active_data.get('RSSI', "0")

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
            self._last_altitude = altitude_now

            _ = graphics.DrawText(
                self.canvas,
                STATS_TEXT_FONT,
                ALTITUDE_X_POS,
                READOUT_TEXT_Y,
                ALTITUDE_TEXT_COLOR,
                altitude_now
            )
            return_flag = True

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
            self._last_speed = speed_now

            _ = graphics.DrawText(
                self.canvas,
                STATS_TEXT_FONT,
                SPEED_X_POS,
                READOUT_TEXT_Y,
                SPEED_TEXT_COLOR,
                speed_now
            )
            return_flag = True

        if not JOURNEY_PLUS and not ENHANCED_READOUT:
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
                self._last_flighttime = flighttime_now

                _ = graphics.DrawText(
                    self.canvas,
                    STATS_TEXT_FONT,
                    right_align(flighttime_now),
                    READOUT_TEXT_Y,
                    TIME_TEXT_COLOR,
                    flighttime_now
                )
                return_flag = True

        else:
            if self._last_rssi != rssi_now:
                if self._last_rssi is not None:
                    _ = graphics.DrawText(
                        self.canvas,
                        STATS_TEXT_FONT,
                        right_align(self._last_rssi),
                        READOUT_TEXT_Y,
                        colors.BLACK,
                        self._last_rssi
                    )
                self._last_rssi = rssi_now

                _ = graphics.DrawText(
                    self.canvas,
                    STATS_TEXT_FONT,
                    right_align(rssi_now),
                    READOUT_TEXT_Y,
                    TIME_TEXT_COLOR,
                    rssi_now
                )
                return_flag = True

        return return_flag

    """ Enhanced readout part 2: Ground track and Vertical Speed """
    @Animator.KeyFrame.add(refresh_speed)
    def p_enhanced(self, count):
        if not self.active_plane_display or not ENHANCED_READOUT:
            self._last_groundtrack = None
            self._last_vertspeed = None
            return True
        X_POS = 39
        GT_Y_POS = 12
        VS_Y_POS = 18
        FONT = fonts.smallest_alt if ALTERNATIVE_FONT else fonts.smallest
        GT_COLOR = colors.groundtrack_color
        VS_COLOR = colors.verticalspeed_color
        return_flag = False

        groundtrack_now = active_data.get('Track', "T▲0°")
        vertspeed_now = active_data.get('VertSpeed', "V 0")

        # Undraw sections
        if self._last_groundtrack != groundtrack_now:
            if self._last_groundtrack is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    FONT,
                    X_POS,
                    GT_Y_POS,
                    colors.BLACK,
                    self._last_groundtrack
                )
            self._last_groundtrack = groundtrack_now

            _ = graphics.DrawText(
                self.canvas,
                FONT,
                X_POS,
                GT_Y_POS,
                GT_COLOR,
                groundtrack_now
            )
            return_flag = True

        if self._last_vertspeed != vertspeed_now:
            if self._last_vertspeed is not None:
                _ = graphics.DrawText(
                    self.canvas,
                    FONT,
                    X_POS,
                    VS_Y_POS,
                    colors.BLACK,
                    self._last_vertspeed
                )
            self._last_vertspeed = vertspeed_now

            _ = graphics.DrawText(
                self.canvas,
                FONT,
                X_POS,
                VS_Y_POS,
                VS_COLOR,
                vertspeed_now
            )
            return_flag = True

        return return_flag

    """ An indicator of how many planes are in the area """
    @Animator.KeyFrame.add(refresh_speed)
    def q_plane_count_indicator(self, count):
        if not self.active_plane_display:
            self._last_activeplanes = None
            return True

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
                colors.plane_count_color,
                self._last_activeplanes
                )
            return True

    """ Switch-time progress bar at the bottom """
    @Animator.KeyFrame.add(refresh_speed)
    def r_switch_progress(self, count):
        if not DISPLAY_SWITCH_PROGRESS_BAR or not self.active_plane_display:
            self._last_switch_progress_bar = None
            return True
        
        plane_count_now = len(relevant_planes)
        BASELINE_Y = 31
        X_START = 0

        # below taken from `print_to_console()`
        select_divisor = 1
        if plane_count_now == 2:
            select_divisor = plane_latch_times[0]
        elif plane_count_now == 3:
            select_divisor = plane_latch_times[1]
        elif plane_count_now >= 4:
            select_divisor = plane_latch_times[2]
        next_select = ((focus_plane_iter // select_divisor) + 1) * select_divisor
        # calculate the fill length based on the current iteration, the planned next select iteration, the associated latch time,
        # and screen width, then align the result to the nearest pixel
        # this moves the progress bar leftward as the next select iteration approaches
        if plane_count_now < 2:
            fill_length = 0
        else:
            fill_length = int(round(((next_select - focus_plane_iter) % (select_divisor + 1)) / select_divisor * RGB_COLS, 0))

        def draw_line(canvas, x_start:int, y_start:int, color, count:int):
            """ draw a horizontal line of given pixel length (this is not graphics.DrawLine) """
            if count is None:
                count = 0
            if count > RGB_COLS:
                count = RGB_COLS
            indicator_color = color
            for i in range(count):
                canvas.SetPixel(
                    x_start + i,
                    y_start,
                    indicator_color.red,
                    indicator_color.green,
                    indicator_color.blue
                )

        if self._last_switch_progress_bar != fill_length:
            if self._last_activeplanes is not None:
                draw_line(
                    self.canvas,
                    X_START,
                    BASELINE_Y,
                    colors.BLACK,
                    self._last_switch_progress_bar
                    )
            self._last_switch_progress_bar = fill_length

            draw_line(
                self.canvas,
                X_START,
                BASELINE_Y,
                colors.switch_progress_color,
                fill_length
                )
            return True

    # ========== Property Controls ===========
    # ========================================
    """ Control the screen brightness """
    @Animator.KeyFrame.add(1)
    def aaa_brightness_switcher(self, count):
        self._last_brightness = self.matrix.brightness
        if active_plane_display and ACTIVE_PLANE_DISPLAY_BRIGHTNESS is not None:
            self.matrix.brightness = ACTIVE_PLANE_DISPLAY_BRIGHTNESS
        else:
            try:
                self.matrix.brightness = current_brightness # read the global commanded brightness
            except:
                self.matrix.brightness = BRIGHTNESS
        if self._last_brightness != self.matrix.brightness:
            # force a redraw of all changing elements as only static elements directly inherit the brightness change
            # recall that if these variables are None, each respective function will attempt to redraw the element
            self._last_time = None
            self._last_date = None
            self._last_day = None
            self._last_seconds = None
            self._last_ampm = None
            self._last_flybys = None
            self._last_track = None
            self._last_range = None
            self._last_callsign = None
            self._last_origin = None
            self._last_destination = None
            self._last_flighttime = None
            self._last_altitude = None
            self._last_speed = None
            self._last_distance = None
            self._last_country = None
            self._last_activeplanes = None
            self._last_latitude = None
            self._last_longitude = None
            self._last_groundtrack = None
            self._last_vertspeed = None
            self._last_rssi = None
            self._last_row1_data = None
            self._last_row2_data = None
            self._last_switch_progress_bar = None
            self._journey_plus_row = None

    """ Actually show the display """        
    @Animator.KeyFrame.add(1)
    def z_sync(self, count):
        # Redraw screen every frame
        _ = self.matrix.SwapOnVSync(self.canvas)

    def run_screen(self):
        while True:
            try:
                # Start loop
                self.play()

            except (SystemExit, KeyboardInterrupt, ImportError):
                return
            
            except Exception as e:
                self.itbroke_count += 1
                if self.itbroke_count > 5:
                    self.a_clear_screen()
                    global DISPLAY_IS_VALID
                    DISPLAY_IS_VALID = False
                    main_logger.critical("*************************************************")
                    main_logger.critical("*   Display thread has failed too many times.   *")
                    main_logger.critical("*        Display will no longer be seen!        *")
                    main_logger.critical("*  Please raise this issue with the developer.  *")
                    main_logger.critical("*************************************************")
                    return
                main_logger.error(f"Display thread error ({e}), count {self.itbroke_count}:\n", exc_info=True)
                time.sleep(5)
                self.a_clear_screen()
                time.sleep(5)
                continue # restart

# =========== Initialization II ============
# ==========================================

timekeeper = threading.Thread(target=timesentinel, name='Clock-Tower', daemon=True)
timekeeper.start()

main_logger.info("Checking for running instances of FlightGazer before continuing...")
matching_processes = match_commandline(Path(__file__).name, 'python')
if len(matching_processes) > 1: # when we scan for all processes, it will include this process as well
    main_logger.critical("FlightGazer is already running! Only one instance can be running!")
    main_logger.warning("Matching processes:")
    for elem in matching_processes:
        process_ID = elem['pid']
        process_name = elem['name']
        process_started = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(elem['create_time']))
        if process_ID != this_process.pid:
            main_logger.warning(f"   PID {process_ID} -- [ {process_name} ] started: {process_started}")
    main_logger.warning(f"This current instance (PID {this_process.pid}) of FlightGazer will now exit.")
    time.sleep(1)
    exit(1)
else:
    del matching_processes
    main_logger.info("Cleared for takeoff.")

configuration_check() # very important
configuration_check_api()
if API_KEY:
    API_session = requests.Session()

get_ip()
CPU_TEMP_SENSOR = get_cpu_temp_sensor()
if CPU_TEMP_SENSOR is not None:
    main_logger.debug(f"CPU temperature sensor: {CPU_TEMP_SENSOR}")
else:
    main_logger.debug("No CPU temperature sensor found or temp readout not supported on this system.")
HOSTNAME = socket.gethostname()
main_logger.info(f"Running from {CURRENT_IP} ({HOSTNAME})")
flyby_stats() # initialize first

# define our scheduled tasks
schedule.every().day.at("00:00").do(runtime_accumulators_reset)
schedule.every().day.at("00:00").do(suntimes)
schedule.every().day.at("23:59").do(flyby_stats) # get us the day's total count before reset
schedule.every().hour.at(":00").do(flyby_stats)
schedule.every().hour.do(get_ip) # in case the IP changes
if rlat is not None or rlon is not None:
    schedule.every().hour.do(read_1090_config) # in case we have GPS attached and are updating location

if DISPLAY_IS_VALID and not NODISPLAY_MODE:
    main_logger.info("Initializing display...")
    if 'RGBMatrixEmulator' in sys.modules:
        main_logger.info("We are using 'RGBMatrixEmulator'")
    else:
        main_logger.info("We are using 'rgbmatrix'")
    display = Display()
    display_stuff = threading.Thread(target=display.run_screen, name='Display-Driver', daemon=True)
    display_fps_thread = threading.Thread(target=display_FPS_counter, name='FPS-Counter', args=(display,), daemon=True)
    brightness_stuff = threading.Thread(target=brightness_controller, name='Brightness-Controller', daemon=True)
    display_sender = threading.Thread(target=DisplayFeeder, name='Info-Parser', daemon=True)    
    display_stuff.start()
    display_fps_thread.start()
    brightness_stuff.start()
    display_sender.start()

dump1090_check()

if DUMP1090_JSON is None and not DISPLAY_IS_VALID:
    main_logger.critical("Unable to successfully connect to dump1090 and no display is available.")
    main_logger.critical("FlightGazer will now exit.")
    time.sleep(3)
    sys.exit(1)

read_1090_config()
session = requests.Session()
""" Session object to be used for the dump1090 polling. (improves response times by ~1.25x) """
suntimes()

def main() -> None:
    """ Enters the main loop. """
    # register our loop breaker
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    periodic_stuff = threading.Thread(target=schedule_thread, name='Scheduling-Thread', daemon=True)
    periodic_stuff.start()
    main_stuff = threading.Thread(target=main_loop_generator, name='Main-Data-Loop', daemon=True)
    airplane_watcher = threading.Thread(target=AirplaneParser, name='Airplane-Parser', daemon=True)
    api_getter = threading.Thread(target=APIFetcher, name='API-Fetch-Thread', daemon=True)
    receiver_stuff = threading.Thread(target=read_receiver_stats, name='Receiver-Poller', daemon=True)
    watchdog_stuff = threading.Thread(target=dump1090Watchdog, name='Dump1090-Watchdog', daemon=True)
    json_writer = threading.Thread(target=export_FlightGazer_state, name='JSON-Writer', daemon=True)
    if WRITE_STATE:
        json_writer.start()

    if INTERACTIVE:
        print("\nInteractive mode enabled. Pausing here for 15 seconds\n\
so you can read the above output before we enter the main loop.")
        print(f"If you need to review the output again, review the log file at:\n\
\'{LOGFILE}\'\n")
        interactive_wait_time = 15
        # silly random distractions while you wait 
        if random.randint(0,1) == 1 and (DISPLAY_IS_VALID and not EMULATE_DISPLAY):
            interactive_wait_time -= 5
            time.sleep(5)
            print("Protip: If you're not using a physical RBG-Matrix display,\n\
        use RGBMatrixEmulator to see the display on a webpage instead!")
        if random.randint(0,1) == 1:
            interactive_wait_time -= 5
            time.sleep(5)
            print("\nDid you know? The color gradient in the FlightGazer logo comes from the\n\
              color scale used on the dump1090 map that corresponds to plane altitude.")
        if random.randint(0,1) == 1:
            interactive_wait_time -= 5
            time.sleep(5)
            print("\nIf you are reading this, WeegeeNumbuh1 says: \"Hi. Thanks for using this program!\"")
            
        time.sleep(interactive_wait_time)
        del interactive_wait_time
    
    if not INTERACTIVE and FORGOT_TO_SET_INTERACTIVE:
        print("\nNotice: It seems that this script was run directly instead of through the initalization script.\n\
Normally, outputs shown here are not usually seen and are written to the log.\n\
\x1b[0;30;43mIf you want to see data, use Ctrl+C to quit and pass the interactive flag (-i) instead.\x1b[0m\n\
If you close this window now, FlightGazer will exit uncleanly.\a\n")

    global dump1090
    dump1090 = "readsb" if is_readsb else "dump1090" # tweak our text output where necessary
    main_logger.debug("Firing up threads...")
    main_stuff.start()
    airplane_watcher.start()
    api_getter.start()
    receiver_stuff.start()
    watchdog_stuff.start()
    main_logger.debug(f"Running with {this_process.num_threads()} threads.")
    print()
    main_logger.info("========== Main loop started! ===========")
    main_logger.info("=========================================") 
    main_logger.removeHandler(main_logger.handlers[0]) # remove the logger stdout stream

    try:
        while True: #keep-alive
            time.sleep(1)
    except ImportError: # catch the display driver (if loaded) exiting and relay it
        sigterm_handler(signal.SIGTERM,"")

# finally
if __name__ == '__main__': main()