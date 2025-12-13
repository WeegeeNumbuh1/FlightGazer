# FlightGazer Display Output Reference
> Intended audience: end-users

## Preface
*This document is equivalent to the tables available in the web-app, under the "Help &amp; Reference" page.*

## Output Reference and Troubleshooting
*Valid for FlightGazer v.9.0.0 and newer*

| Output | Meaning / Cause | Remedy / Information |
|---|---|---|
| **Show Even More Info**<br>"LADD Aircraft" | Limiting Aircraft Data Displayed \- *"Please don't track me*\." | [More Information](https://www.faa.gov/air_traffic/technology/equipadsb/privacy) |
| **Show Even More Info**<br>"PIA Aircraft" | \(U\.S\. only\) Privacy ICAO Address \- *"Good luck figuring out who I am\."* | [More Information](https://www.faa.gov/air_traffic/technology/equipadsb/privacy) |
| **Show Even More Info**<br>"TIS-B Contact" | Traffic Information Service – Broadcast - broadcast information sent by ground stations corresponding to an aircraft; cannot be tied to a registration or aircraft type and is used for collision avoidance. | [More Information](https://en.wikipedia.org/wiki/Traffic_information_service_%E2%80%93_broadcast) |
| **Clock**<br><code>FLYBY TRKG RNGE</code><br><code>N/A   N/A  N/A</code><br>\- or \-<br><code>FLYBY TRKG RNGE</code><br><code>123   N/A  N/A</code> | - Failed to connect to receiver at startup\.<br>- Communication with the receiver has temporarily stopped due to instability\. | - Receiver service (<code>dump1090</code>) is not running/stopped\. Check for errors for that service\.<br>- The SDR hardware or its connection (USB port, cables, etc.) may be degraded. Check on these components\.<br>- The current system may be overloaded\. Check on the system\.<br>- If operating on a remote instance of dump1090, check the network or remote system\.<br>- Additionally, check the FlightGazer logs\.<br>- After fixing the underlying issue, restart FlightGazer\. |
| **Clock**<br><code>FLYBY TRKG RNGE</code><br><code>N/A   123  N/A</code> | Location is not set in receiver\. | - Set your location for dump1090\. Then, restart FlightGazer\.<br>- Advanced: if using a GPS receiver on the system, check to see if the service is running and has obtained a GPS fix\. |
| **Journey**<br><code>--- ▶ ---</code> | - Waiting for API to send a result\.<br>- API is not in use\.<br>- An API limit has been reached\.<br>- Aircraft is on the ground\. | Normal occurrence\. |
| **Journey**<br><code>N/A ▶ ---</code> | - Aircraft blocked from tracking\.<br>- Aircraft detected before API was able to\. | For aircraft that are not blocked from tracking: try using a lower FLYBY_STALENESS value\. |
| **Journey**<br><code>latitude ▶ longitude</code> | API returned a result that could not be associated with an airport\. | Rare, but normal occurrence\. |
| **Journey**<br><code>!API ▶ FAIL</code> | API call for this flight failed\. | - API service may be down, wait until the service is restored\.<br>-You might have been rate limited. If this keeps happening, try using a smaller RANGE\.<br>- You may have an issue with your API key\. Contact FlightAware\. |
| **Journey**<br><code>\!CON ▶ FAIL</code> | Could not connect to the API\. | Check your network connection\. |

## Clock Center Row and Abbreviations
*Valid for FlightGazer v.9.6.0 and newer*

| Layout | Description |
| --- | --- |
| `▲--:-- ▼--:--` | Sunrise & Sunset |
| `G##.# N##.# L##%` | `G` = Receiver gain<br>`N` = Noise (negative value, higher is better)<br>`L` = Loud signals (percentage, lower is better) |
| `ABC wk## d###` | `ABC` = Month abbreviation<br>`wk` = Week number of the year<br>`d` = Day number of the year<br> |
| `##.#° ABCD ▼##` | Outside temperature (Celcius or Fahrenheit)<br>`ABCD` = Prevailing weather condition<br>Wind direction and speed (knots, mph, or m/s) |
| `D##° V#.# C####` | `D` = Dew point (same unit as temperature)<br>`V` = Visibility (miles or kilometers)<br>`C` = Estimated cloud base (feet or meters) |

### Weather condition meanings
*Modifiers:*
`+` = Heavy `-` = Light

*Note: These are not all possible outputs, just the abbreviated ones.*
| Weather Abbreviation | Description |
| --- | --- |
| `TSTM` / `TSM` | Thunderstorm |
| `DRZL` / `DZL` | Drizzle |
| `RN` | Rain |
| `FZRN` | Freezing Rain |
| `SHWR` / `SHR` | Rain Showers |
| `SNW` | Snow |
| `RSMX` | Mixed Rain and Snow |
| `SSHR` | Snow Showers |
| `SMKE` | Smoke |
| `SQLL` | Squall |
| `CLR` | Clear Sky |
| `cFEW` | Few Clouds |
| `cSCT` | Scattered Clouds |
| `cBKN` | Broken Clouds |
| `OVRC` | Overcast |
