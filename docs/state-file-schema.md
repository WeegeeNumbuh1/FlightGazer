# Interpreting the FlightGazer State File `current_state.json`
> Intended audience: developers

## Preface
The `current_state.json` is written to `/run/FlightGazer` when the main FlightGazer python script is running, by default.<br>
It is updated at the end of each update interval `LOOP_INTERVAL` (by default 2 seconds, can be 1 if `FASTER_REFRESH` is set).
Atomicity is not guaranteed.

This file will not be present if:
- FlightGazer is not running
- The `WRITE_STATE` setting is set to `False`
- FlightGazer is unable to write to `/run/FlightGazer`

It's possible for this file to remain present if FlightGazer crashes unexpectedly (and doesn't do its shutdown routine) or is `SIGKILL`'d, at which point the data present in the file represents the last valid state of FlightGazer.<br>
Each section that follows represents each root key present in the JSON and all of its subkeys. All keys are assumed to be present unless otherwise noted.<br>

This JSON represents the values of *global* variables tracked within the program. Yes, you read that right, these are all values which are accessible in a global scope. This JSON is serialized after all the processing threads within FlightGazer complete their work, which serves as both an internal processing optimization and to ensure data consistency at the end of each `LOOP_INTERVAL`.<br>

As a beneficial side-effect, this document also serves as a reference for the meanings behind all the globals as well.<br>

> *There are a total of 200 available keys, not counting the root keys.*<br>
> *Valid for FlightGazer v.9.7.1 and newer*

## `FlightGazer`
Represents overall state and the current main settings.

| key | description | schema | example |
| --- | --- | --- | --- |
| `start_date` | ISO 8601 date when FlightGazer was started | str | "2025-01-01T12:34:56" |
| `start_time` | Monotonic reference time when FlightGazer was started | float | 98.64142 |
| `runtime` | How long FlightGazer has been running | str | "42 days, 16:24:38" |
| `version` | Version of the main python script, `---` separates the version and the release date | str | "v.9.0.0 --- 2025-10-22" |
| `config_version` | Version of the config file loaded by FlightGazer | str, null | "v.9.0.0" |
| `refresh_rate_sec` | How often FlightGazer polls the dump1090 `aircraft.json` file, in seconds | int | 2 |
| `distance_unit` | What unit is used when interpreting distances | str | "nmi" |
| `speed_unit` | What unit is used when interpreting speed | str | "kt" |
| `altitude_unit` | What unit is used when interpreting altitude | str | "ft" |
| `clock_24hr` | True if time shown on the display is using a 24 hour format | bool | false |
| `sunrise_and_sunset` | Calculated sunrise and sunset times (in either 12 or 24 hour format) corresponding to the current site location. If these values cannot be determined, this key is null. | array, null | ["5:21a", "8:32p"] |
| `filter_settings` | Dictionary representing the parameters used for detailed tracking | object | (see below) |

> *12 keys*

### `filter_settings` subkey
| key | description | schema | example |
| --- | --- | --- | --- |
| `range_limit` | Aircraft within this radius from the site location will be considered for detailed tracking | float, int | 2 |
| `height_limit` | Aircraft below this altitude will be considered for detailed tracking | float, int | 15000 |
| `location_timeout_sec` | Aircraft which do not report a location after this amount of time (in seconds) will be dropped from overall tracking | int | 60 |
| `flyby_staleness_min` | Time (in minutes) which influences flyby counts and API usage; aircraft seen in the tracking area again before this time will not count towards the flyby count | int | 30 |
| `follow_this_aircraft` | If the `FOLLOW_THIS_AIRCRAFT` setting was provided a valid ICAO hex, this aircraft will be tracked when it is detected by the receiver; null otherwise | str, null | "a00002" |

> *5 keys*

## `receivers`
Represents stats based on the ADS-B site and related hardware.

| key | description | schema | example |
| --- | --- | --- | --- |
| `dump1090_is_available` | Whether an aircraft decoder (dump1090 / readsb) is currently available; this is false if the watchdog is triggered or a decoder was not found on startup | bool | true |
| `dump1090_json` | URL or filesystem path of the dump1090 `aircraft.json` used as data source; null if not connected | str, null | "/run/readsb/aircraft.json" |
| `dump978_json` | URL or filesystem path of the dump978 `aircraft.json`, if present; null otherwise | str, null | "/run/skyaware978/aircraft.json" |
| `using_filesystem` | True if the dump1090 JSON is being read from the local filesystem instead of over the network | bool | true |
| `using_filesystem_978` | True if the dump978 JSON is being accessed from filesystem | bool | true |
| `dump1090_type` | Identifies the type of decoder detected, "dump1090" or "readsb" | str, null | "dump1090" |
| `location_is_set` | Whether dump1090 is configured with a site location | bool | true |
| `response_time_ms` | Response time for fetching the dump1090 JSON (in milliseconds) | float | 0.123 |
| `dump1090_json_data_age_sec` | Calculated age in seconds of the last dump1090 JSON file's data | float | 0.344 |
| `dump978_json_data_age_sec` | Calculated age in seconds of the last dump978 JSON file's data, or null if dump978 not present | float, null | 1.601 |
| `polling_drift_correction_ms` | Correction applied to adjust for polling drift between this process and the dump1090 JSON (in milliseconds) | float | -0.064 |
| `json_size_KiB` | Size of the dump1090 JSON in KiB at this current poll | float | 112.142 |
| `json_transfer_rate_MiB_per_sec` | Effective transfer rate for the dump1090 JSON file | float | 46.746 |
| `json_processing_time_ms` | Time spent parsing/processing the dump1090 JSON (in milliseconds) | float | 1.351 |
| `json_processing_rate_MiB_per_sec` | Data processing throughput for the dump1090 JSON | float | 162.145 |
| `filtering_and_algorithm_time_ms` | Time spent filtering the incoming data and running the selection algorithm (in milliseconds) | float | 7.322 |
| `receiver_stats` | Short dictionary of averaged receiver metrics - see `receiver_stats` section below | object | {"Gain": 32.8, "Noise": -28.6, "Strong": 0.046} |

> *17 keys*

### `receiver_stats` subkey
Short dictionary describing the receiver's computed statistics.
| key | description | schema | example |
| --- | --- | --- | --- |
| `Gain` | Receiver gain (unitless value as reported from the receiver) | float, null | 32.8 |
| `Noise` | Measured noise floor in decibels (negative value) | float, null | -28.6 |
| `Strong` | Percent of packets deemed strong (>3dBFS) as a percentage | float, null | 0.046 |

> *3 keys*

## `plane_stats`
Represents aircraft-specific stats. Any aircraft within the designated tracking area are also described here in the `relevant_planes` key.

| key | description | schema | example |
| --- | --- | --- | --- |
| `currently_tracking` | Total number of aircraft currently being tracked by the receiver | int | 246 |
| `current_range` | Distance of the farthest aircraft currently detected by the receiver | float | 316.24 |
| `flybys_today` | Number of aircraft that were tracked in the configured tracking area today (resets at midnight) | int | 98 |
| `last_unique_plane` | Record for the last aircraft seen today - see the `last_unique_plane` section below | object, null | {"ID": "a00002", "Time": 4780.658841, "Flyby": 98} |
| `aircraft_selections` | Total times the aircraft selection algorithm has changed the focused aircraft | int | 1260 |
| `rare_selection_events` | Count of times the selection algorithm used the rare-events compensation logic (aircraft count changed when an aircraft needed to be selected) | int | 24 |
| `high_priority_events` | Count of selection overrides triggered by aircraft entering the high-priority dome around the site (<0.4 nmi line-of-sight) | int | 4 |
| `average_relevant_planes_in_area` | Average number of tracked aircraft present in the tracking area; >= 1 | float | 1.624 |
| `average_algorithm_active_time_sec` | Average amount of time the selection algorithm remains active (seconds) | float | 138.91 |
| `algorithm_use_today` | Total time the selection algorithm has been used today (HH:MM:SS) | str | "02:12:31" |
| `no_filter` | Whether FlightGazer is currently running in `NOFILTER` mode | bool | false |
| `focus_plane_iter` | How many cycles the selection algorithm is active, 0 if no aircraft are present | int | 21 |
| `focus_plane_ids_discard` | List of aircraft IDs previously tracked by the selection algorithm | array | ["a00002", "..."] |
| `focus_plane_ids_scratch` | Scratchpad list of currently tracked aircraft IDs for the selection algorithm | array | ["a00002", "ad8421", ...] |
| `focus_plane` | ICAO hex of the currently focused aircraft (or null if none available) | str, null | "a00002" |
| `high_priority_plane` | True if the currently focused aircraft is in the high-priority dome | bool | false |
| `in_range` | Number of relevant aircraft in the current `relevant_planes` array | int | 3 |
| `relevant_planes` | Detailed list of nested objects describing each tracked aircraft the tracking area, null if `NOFILTER` mode is enabled | array, null | (see `relevant_planes` subkey below) |

> *18 keys*

### `relevant_planes` subkey
An array of nested objects which represents current data for each aircraft considered for detailed tracking. The array is empty when there are no aircraft available. This key is null if running in `NOFILTER` mode.

| key | description | schema | example |
| --- | --- | --- | --- |
| `Flight` | Callsign (falls back to registration and finally to ICAO hex) | str | "RPA123" |
| `Country` | Two-letter ISO country code based on ICAO hex of the aircraft | str | "US" |
| `Altitude` | Altitude of the aircraft in the selected units (0 if unknown or on ground) | float | 36500 |
| `Speed` | Ground speed in selected units (0 if unknown) | float | 546.2 |
| `Distance` | Distance from site in selected unit (0 if location unknown) | float | 1.262 |
| `Direction` | Cardinal direction from the site, empty string if location unknown | str | "NW" |
| `DirectionDegrees` | Degree direction relative to site; 0 if location unknown | float | 292.0 |
| `Latitude` | Current latitude of the aircraft | float | 40.123456 |
| `Longitude` | Current longitude of the aircraft | float | -73.123456 |
| `Track` | Track over ground in degrees | float | 292.0 |
| `VertSpeed` | Rate of altitude change in configured units | int, float | -640.0 |
| `RSSI` | Average signal strength in dBFS | float | -18.1 |
| `Elevation` | Calculated elevation angle of the aircraft from the site in degrees | float | 34.257 |
| `SlantRange` | Direct line-of-sight distance from the site in selected units | float | 1.47882 |
| `Operator` | Airline operator based on data from the Federal Aviation Administration, Directive No. JO 7340.2N, Chapter 3, Section 3, or null if unknown | str, null | "REPUBLIC AIRLINES, INC. (INDIANAPOLIS, IN)" |
| `Telephony` | Operator's telephony based on data from Federal Aviation Administration, Directive No. JO 7340.2N, Chapter 3, Section 3; null if unknown | str, null | "BRICKYARD" |
| `OperatorAKA` | More commonly known operator name; null if unknown | str, null | "Republic Airways" |
| `Owner` | Registered owner of the aircraft, if available | str, null | "TVPX AIRCRAFT SOLUTIONS INC TRUSTEE" |
| `ICAOType` | ICAO type code for the aircraft model, or "None" | str | "A320" |
| `CategoryDesc` | ADS-B category description for the aircraft, or "None" | str | "Large (75000-300000 lbs)" |
| `AircraftDesc` | Aircraft model and year, if available | str, null | "2006 Boeing 737-700" |
| `TrackingFlag` | Special aircraft flag if present, "LADD", "PIA", "Military", "Other", or "None" | str | "LADD" |
| `Registration` | Aircraft registration string, if available | str, null | "N123AB" |
| `Squawk` | 4-digit octal code assigned by ATC | str | "1203" |
| `Priority` | FlightGazer internal integer representation of the broadcast data type; lower = better, 0 if the source is not provided | int | 1 |
| `Source` | Source of the data, either "ADS-B" or "UAT" | str | "ADS-B" |
| `OnGround` | Additional context for when altitude is reported to be 0 | bool | false |
| `Distressed` | True if the aircraft is squawking emergency codes 7500/7600/7700 | bool | false |
| `NavigationAccuracy` | Navigation accuracy of positions reported by the aircraft, in meters | int, null | 9 |
| `ApproachRate` | Calculated approach speed of the aircraft in relation to the side based on speed unit; always 0 in `NOFILTER` mode, negative means moving away from the site | float | -184.6 |
| `FutureLatitude` | Estimated future latitude of the aircraft in the next data packet (`refresh_rate_sec` in the future); null if not estimated | float, null | 40.123500 |
| `FutureLongitude` | Estimated future longitude of the aircraft in the next data packet (`refresh_rate_sec` in the future); null if not estimated | float, null | -73.12340 |
| `FutureDistance` | Estimated future distance based on `FutureLatitude` and `FutureLongitude`; null if not estimated | float, null | 1.315572 |
| `Flyby` | Cardinal flyby index for the aircraft (e.g. "this is the 98th aircraft flyby today") | int | 98 |
| `Staleness` | Age of the position data for the aircraft (seconds) | float | 2.543 |
| `Timestamp` | Monotonic timestamp for this packet | float | 426314.11258 |

> *36 keys*

### `last_unique_plane` subkey
| key | description | schema | example |
| --- | --- | --- | --- |
| `ID` | ICAO hex ID of this aircraft | str | "a00002" |
| `Time` | Monotonic timestamp this aircraft was first seen | float | 4780.658841 |
| `Flyby` | Flyby number of this aircraft | int | 98 |

> *3 keys*

## `api_stats`
Represents API-related information from FlightAware.

| key | description | schema | example |
| --- | --- | --- | --- |
| `api_enabled` | Whether an API key is valid (and API calls are enabled) | bool | true |
| `api_key` | Masked API key used for calls (last 5 characters visible) | str, null | "*****TCHYN" |
| `successful_calls` | Number of successful API calls for the current day | int | 80 |
| `failed_calls` | Number of failed API calls for the current day | int | 0 |
| `calls_with_no_data` | Number of calls that returned no data or where the aircraft was blocked from tracking | int | 2 |
| `cache_hits` | Number of times API results were served from cache | int | 32 |
| `baseline_use` | API usage baseline (currency) at script start and updated at midnight | float | 8.395 |
| `cost_today` | Estimated API cost consumed today based on calls executed | float | 1.250 |
| `estimated_use` | Combined baseline and current estimated API usage | float | 9.645 |
| `api_cost_limit_reached` | Whether the configured API cost limit was reached today | bool | false |
| `api_daily_limit_reached` | Whether the configured daily API call limit was reached today | bool | false |
| `api_schedule_triggered` | Whether the API schedule has currently disabled calls | bool | false |
| `last_api_response_time_ms` | Last API call round-trip time (milliseconds) | float | 1260.5 |
| `last_api_result` | The last API result; null if the API hasn't been used | object, null | (see below) |

> *14 keys*

### `last_api_result` subkey
Latest result as received by the API.

| key | description | schema | example |
| --- | --- | --- | --- |
| `ID` | ICAO hex ID of the aircraft associated with this API call | str | "a00002" |
| `Flight` | Callsign used for API lookup | str | "DAL123" |
| `Origin` | Origin airport code, or null | str, null | "JFK" |
| `Destination` | Destination airport code, or null | str, null | "LAX" |
| `OriginInfo` | Array with origin airport name and city, or nulls | array | ["John F. Kennedy Intl", "New York"] |
| `DestinationInfo` | Array with destination airport name and city, or nulls | array | ["Los Angeles Intl", "Los Angeles"] |
| `Departure` | ISO time the aircraft first became airborne or was detected by the API, or null | str, null | "2025-01-01T12:12:12+00:00" |
| `Status` | Internal FlightGazer API status flag (0 = success, 1 = blocked/no data, 2 = non-200 HTTP result, 3 = connection failure) | int | 0 |
| `APIAccessed` | Monotonic timestamp of when this API call was executed | float | 654211.4865 |

> *9 keys*

## `database_stats`
Represents database-related stats.

| key| description | schema | example |
| --- | --- | --- | --- |
| `database_connected` | Whether a connection to the local database exists and is valid | bool | true |
| `database_version` | Version string of the database when first connected (null if no connection at startup) | str, null | "3.14.1769" |
| `total_queries` | Total number of database queries performed | int | 324 |
| `empty_results` | Count of queries that returned no data | int | 21 |
| `errors` | Number of failed database queries | int | 0 |
| `average_response_times_ms` | Average response time for database queries in milliseconds | float | 4.23 |
| `last_response_time_ms` | Last query response time in milliseconds | float | 3.21 |

> *7 keys*

## `display_status`
Represents display-related information.

| key | description | schema | example |
| --- | --- | --- | --- |
| `no_display_mode` | Whether the display is disabled and only console output is used | bool | false |
| `display_is_valid` | Whether the display is functional (initialized correctly and is available) | bool | true |
| `driver` | String identifying which display driver is in use, either "rgbmatrix" or "RGBMatrixEmulator", null otherwise | str, null | "rgbmatrix" |
| `journey_plus_enabled` | True if the `JOURNEY_PLUS` layout is enabled | bool | false |
| `enhanced_readout_enabled` | True when `ENHANCED_READOUT` is the only active plane display layout | bool | true |
| `enhanced_readout_fallback_running` | True if `ENHANCED_READOUT` is currently being used in place of journey information | bool | false |
| `show_even_more_info` | True if the scrolling marquee to show aircraft and detailed journey info is enabled | bool | true |
| `display_formatting_time_ms` | The time spent formatting screen data (milliseconds) | float | 0.846 |
| `fps` | The current animation frames-per-second | float | 25.1 |
| `render_time_ms` | The average time taken to render the animation frames, in milliseconds | float | 4.667 |
| `current_brightness` | Current brightness level for display (0-100), or null when invalid | int, null | 100 |
| `current_mode` | Which display mode is active: "active (plane display)" or "idle (clock)", null otherwise | str, null | "idle (clock)" |
| `data_for_screen` | The actual data dictionary sent to the screen, or null if `display_is_valid` is false | object, null | See `data_for_screen` tables below |

> *13 keys*

### `data_for_screen` subkey
Represents the internal data sent to the display to render. This key is null if `display_is_valid` is false, but has two different variants based on the `current_mode` value:

#### Idle
| key | description | schema | example |
| --- | --- | --- | --- |
| `Flybys` | Number of aircraft flybys today | str | "0" |
| `Track` | Number of aircraft currently being tracked | str | "321" |
| `Range` | Distance of the farthest aircraft as detected by the receiver | str | "64.3" |

> *3 keys*

#### Active
| key | description | schema | example |
| --- | --- | --- | --- |
| `Callsign` | Callsign displayed for the active aircraft, max length of 8 characters | str | "UAL1" |
| `Origin` | Origin airport code, max length of 5 characters | str | "LAX" |
| `Destination` | Destination airport code, max length of 6 characters | str | "SIN" |
| `FlightTime` | Formatted string representing time aircraft spent airborne | str | "10h12m" |
| `Altitude` | Altitude formatted for display in configured altitude unit, or "GRND" if the aircraft is on the ground | str | "12550" |
| `Speed` | Ground speed formatted for display using selected units | str | "260" |
| `Distance` | Cardinal direction and distance to the aircraft formatted for the display, always 5 characters | str | "SW1.4" |
| `Country` | Two-letter ISO country code of the aircraft based on ICAO | str | "US" |
| `Latitude` | Formatted latitude for the aircraft | str | "40.123N" |
| `Longitude` | Formatted longitude for the aircraft | str | "73.142E" |
| `Track` | Track in degrees for on-screen, with associated direction arrow | str | "T◣241°" |
| `VertSpeed` | Formatted vertical speed for display | str | "V+4000" |
| `RSSI` | Formatted signal strength for display. Not strictly negative (can be positive for the case of UAT signals) | str | "-18.1" |
| `AircraftInfo` | String representing aircraft info and journey data, if available; aircraft description \| operator/owner \-\-\- detailed journey details/other messages | str | "2025 BOEING 787-8 Dreamliner \| United Airlines \-\-\- San Francisco to Singapore (San Francisco Intl to Singapore Changi)" |
| `is_UAT` | Data for this aircraft was sourced from dump978 | bool | false |

> *15 keys*

## `weather_data` (Only present if the Weather API is enabled)
Weather information returned by the OpenWeatherMap API for the site location.

| key | description | schema | example |
| --- | --- | --- | --- |
| `site_name` | Location name of the site as reported by the API (usually city or region name) | str, null | "Townsville" |
| `condition` | Short code for the prevailing weather condition, meant for the display; max length of 4 characters | str | "-RN" |
| `condition_desc` | More detailed description of the current weather condition | str | "light rain" |
| `temp` | Current air temperature (depends on `temp_unit`) or null if unavailable | float, null | 12.1 |
| `humidity` | Current humidity percent, or null | int, null | 43 |
| `dew_point` | Calculated dew point based on `temp` and `humidity`, or null | float, null | 6.1 |
| `wind_speed` | Current wind speed (units depend on `wind_speed_unit`) | float, null | 4.0 |
| `wind_dir` | Wind direction in degrees (or null if zero wind) | int, null | 210 |
| `wind_gust` | Wind gust in same units as `wind_speed`; null if not measured | float, null | 7.4 |
| `ceiling` | Calculated cloud base elevation based on `temp` and `dew_point` | float, null | 3500 |
| `cloudiness` | Percent sky cover; null if unknown | int, null | 90 |
| `visibility` | Current visibility distance using `distance_unit` | float, null | 5.2 |
| `elevation` | Calculated elevation of the site, based on pressure data, or null | float, null | 268.0 |
| `pressure` | Sea-level corrected pressure | float, null | 1012.3 |
| `pressure_raw` | Raw ground pressure based on site location | float, null | 1010.5 |
| `temp_unit` | Temperature unit used by weather data (F or C) | str | "C" |
| `wind_speed_unit` | Unit for wind speeds (m/s, kt, or mph) | str | "m/s" |
| `distance_unit` | Distance unit used in weather responses (mi or km) | str | "km" |
| `pressure_unit` | Unit used for pressure values (hPa or inHg) | str | "hPa" |
| `ceiling_elevation_unit` | Unit for `ceiling` and `elevation` (ft or m) | str | "m" |
| `API_key` | Masked weather API key in use (last 5 characters visible) | str, null | "*****b12ab" |
| `response_time_ms` | Round trip response time from weather API (milliseconds) | float, null | 578.6 |
| `successful_calls` | Total successful calls to weather API since start | int | 196 |
| `failed_calls` | Total failed calls to weather API since start | int | 1 |
| `timestamp` | Unix time of last successful API result as reported from the API | int, null | 1690000000 |

> *25 keys*

## `runtime_status`
Various runtime flags and stats for this current running session of FlightGazer.

| key | description | schema | example |
| --- | --- | --- | --- |
| `interactive_mode` | Whether FlightGazer is running in interactive console mode | bool | true |
| `last_console_print_time_ms` | Time taken to print the last console output (milliseconds) | float | 12.611 |
| `last_json_export_time_ms` | Time taken to serialize and write the previous iteration of the state file (milliseconds) | float | 3.479 |
| `total_data_processed_GiB` | Total amount of data processed by FlightGazer in GiB | float | 28.412553 |
| `estimated_time_offset_sec` | Estimated offset (seconds) between this process and dump1090 | float | 0.004321 |
| `verbose_mode` | True if verbose logging is enabled | bool | false |
| `inside_tmux` | Whether this instance is running inside a `tmux` session | bool | true |
| `flyby_stats_present` | Whether the `FLYBY_STATS_FILE` (`flybys.csv`) is present and writable | bool | true |
| `watchdog_triggered` | True if the dump1090 watchdog is currently triggered | bool | false |
| `dump1090_failures` | Number of times the JSON polling failed | int | 1 |
| `watchdog_triggers` | Number of times the watchdog has triggered in this session | int | 0 |
| `really_active_adsb_site` | True if the connected dump1090 instance experiences high traffic | bool | false |
| `really_really_active_adsb_site` | `really_active_adsb_site` but even more active (you unlock some achievements with this one) | bool | false |
| `range_too_large` | True if configured `RANGE`/`HEIGHT_LIMIT` combination is too large for local traffic, keeping the selection algorithm needlessly active | bool | false |
| `combined_feed` | True if multiple dump1090 feeds are being combined on this currently connected instance | bool | false |
| `display_failures` | Count of display failures for this session (null if display disabled) | int, null | 0 |
| `cpu_percent` | CPU usage percent for this process (normalized) | float | 18.41 |
| `cpu_temp_C` | CPU temperature in Celsius, if available; otherwise null | float, null | 50.3 |
| `memory_MiB` | Process memory usage in MiB | float | 15.34 |
| `pid` | System PID for the current process | int | 1234 |

> *20 keys*

## `time_now`
Current time the JSON was generated, in ISO 8601 format as a string and approximated to the nearest second.