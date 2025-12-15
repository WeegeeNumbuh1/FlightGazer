# Known Issues and Shortcomings with FlightGazer
> Intended audience: end-users, developers

## Preface
This document serves as a reference list of previous issues (which may be partially or fully solved) and existing shortcomings due to FlightGazer's architecture.<br>
These used to be listed as part of the main readme file, but has been separated out into this document to declutter that readme.
- signed: WeegeeNumbuh1

## Current Shortcomings
### `No Filter` mode can be used to artifically inflate flyby count
- FlightGazer has a feature where it will write out stats before shutting down so that it can reload those stats upon restart (if it's the same day). The flyby count is simply a number and has no additional information such as the IDs of aircraft
- Upon reload, FlightGazer fills in dummy IDs equal to the value of the last written flyby count in its internal list of aircraft IDs it keeps track of for flybys
- The flyby count runs under the assumption that the flyby area itself is small, but since `No Filter` removes that restriction, it's a free-for-all
- This is not usually a problem, as long as we don't restart often in the same day
- May not ever get fixed

### Flyby stats are dependent on `FLYBY_STALENESS` and the combination of `HEIGHT_LIMIT` and `RANGE`
- Flyby stats are not 100% accurate, but can reasonably treated as so as long as the aforementioned settings are reasonable for the local traffic
  - Example where inaccuracy is possible: a helicopter hovering within the designated tracking area along with the shortest possible `FLYBY_STALENESS` value. If the helicopter stays within the area for longer than the `FLYBY_STALENESS` value, it will raise the counter
  - When using `No Filter` mode, `FLYBY_STALENESS` influences the amount of flights seen as it uses the same flyby tracking logic
    - Therefore, FlightGazer's metrics for counting "unique aircraft seen" (aka "flights") in this mode might vary significantly if compared to other tacking services
- `FLYBY_STALENESS` was introduced in v.1.3.0 to solve the initial problem of how the internal flight counter worked at the time:
  - Earlier versions of FlightGazer used a `set` as a naive way to count flybys
  - If the same aircraft appeared again later in the day, it wouldn't count as another flyby
- `FLYBY_STALENESS` was tied to the API results cache in v.2.10.0 to minimize making new API calls, especially for cases of touch-and-go landings
  - Thus, the flyby count has a bias towards lower numbers
- The current algorithm in place was designed for the way FlightGazer does its polling, which is *stateless*

## Previous Issues
### Duplicate entries for the same aircraft
- On rare occasions are times when there will be two entries of the same aircraft
  - This is a common case that's been noted since the v.0.x days, mainly due to a dual (ADS-B + UAT) receiver setup
  - It was determined to occur with aircraft that uses a dual mode transponder or there is ADS-R contact of the same aircraft on UAT while it's present over ADS-B
  - At the time, this surprisingly did not break functionality
- **This was first mitigated in v.2.6.3 and fully rectified in v.5.0.0**
  - v.2.6.3 simply used a "first-come, first-served" approach, where the first instance of the same aircraft was used
    - This did not necessarily represent the *best* information source for the aircraft as at times FlightGazer would latch onto ADS-R data, which led to instances of using stale data (e.g. the aircraft has long left the tracking area but the last data packet with location was inside the tracking area)
      - The introduction of `LOCATION_TIMEOUT` in v.2.3.0 was actually created to handle this case at the time
  - v.5.0.0 introduced a priority-based deduplication algorithm which almost solves this issue
    - This algorithm is not infallable as it relies on more modern dump1090 builds/readsb to embed the broadcast type in the data; in the absence of this, the algorithm becomes functionally equivalent to the method introduced in v.2.6.3

### FlightGazer isn't able to propagate a failure status when running as a service
- With the way FlightGazer is run (inside `tmux` to ensure persistence), any unhandled error that leads to it crashing is not propagated
- **Versions v.9.1.0 and newer now write a file in** `/run/FlightGazer` **if FlightGazer ends up in a degraded state or quits due to an uncorrectable error.**
- This issue is not fully fixed but has been mitiaged somewhat, as long as the main python script is able to run
  - Syntax errors tend to be the Achilles Heel in this case; the service will start successfully, but because `tmux` exits once there is nothing running, it will return an exit code of `0`.