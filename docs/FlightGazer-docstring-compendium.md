# Collection of Reference Docstrings Explaining how tf FlightGazer Works Internally
> Intended audience: developers and the code-curious

## Preface
*These docstrings reside inside the main python file and exist here for "easier" access.*<br>
*Future releases may eventually remove these docstrings from the main script, but as of this document, they still remain there.*

It's recommended to have this open in another window or screen in order to maintain your sanity pouring through the great lasagna I cooked up. Or, maybe you're just curious and questioning to yourself how I even came up with these overly convoluted approaches. (Answer: idk, lmao)<br>
If you'd like to see descriptions for all the globals used in the script, those exist in the [`state-file-schema`](/docs/state-file-schema.md) readme.
- signed: WeegeeNumbuh1

## Thread Signaling Layout
    ----- Thread Signaling Layout -----

    ░░░ main_loop_generator() ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
    ░       loop()                                                                              ░
    ░         ├- -<- - - -<- - - -<- - - -<- - - -<- - - -<- - - -<- - - ┐                      ░
    ░         ├───► dump1090_hearbeat() ► dump1090_loop() ► ─┐           ▲ (transient event)    ░
    ░         └───< sleep for LOOP_INTERVAL <────<─┬──<────◄─┴─► Exception Handling             ░
    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ | ░░░░░░░░░           ▼ (if too many errors) ░
                ┌────────────────┬──────────────┬──┘         ░           |                      ░
                ▼                ▼              ▼            ░░░░░░░░░░░ ▼ ░░░░░░░░░░░░░░░░░░░░░░
        [AirplaneParser]   [synchronizer]   [DistantDeterminator]      [dump1090Watchdog]
                |
                ├────────────────┬──────────────────┐               extract_API_results()
                ▼                ▼                  ▼                         |
          [APIFetcher]1   [DisplayFeeder]2   [PrintToConsole]3                |
             5▲ ▲                |4                 ▼                         |
              | └- - - - - - - - ┘             [WriteState]                   |
              |                                                               |
              └ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ┘

    1 = Only executes completely when the following are true:
        - API_KEY exists                 | set only on startup
        - NOFILTER_MODE is False         | set only on startup
        - api_limiter_reached() is False | can change during runtime
        - ENHANCED_READOUT is False      | can change during runtime

    2 = Always runs, unless: NODISPLAY_MODE is True or DISPLAY_IS_VALID is False
        - NODISPLAY_MODE   | set only on startup
        - DISPLAY_IS_VALID | can change during runtime

    3 = Only executes completely when INTERACTIVE is True, always sends a signal
        to WriteState

    4 = If ENHANCED_READOUT_AS_FALLBACK is True, there exists a Condition
        so that APIFetcher can wait until DisplayFeeder is done and evaluate
        the value of ENHANCED_READOUT

    5 = If extract_API_results() encounters a stale result, it will trigger
        the API fetcher outside of the normal signaling path. This occurs
        when the API result expires while the focus plane is selected and there
        are no other planes in the area to naturally cause AirplaneParser to
        initiate the normal work chain. When running normally, both DisplayFeeder
        and PrintToConsole will try to trigger the API fetcher almost simultaneously,
        however, as signal calls are queued, only the first call will succeed. The
        subsequent call will then cause the handler to finish early as there is now
        a result from the previous call. With the lasagna architecture in place,
        the next loop or two (depending on how fast the API responds) will read
        the result of this forced API refresh, as designed. Additional note:
        when the normal signal chain is traversed with a stale entry in the results deque,
        the API fetcher will handle the signal from AirplaneParser first, then
        the calls from extract_API_results() will follow.

## Selection Algorithm Notes
> *tl;dr this code is cooked, bro. Must've been an Italian in a past life with how much spaghetti is in here.*<br>

    The selector algorithm is rather naive, but it works for occurrences when there is more than one plane in the area
    and we want to put some effort into trying to go through all of them without having to flip back and forth constantly at every data update.
    It is designed this way in conjunction with the `focus_plane_api_results` cache and `focus_plane_iter` modulo filters to minimize making new API calls.
    Additionally, it avoids the complications associated with trying to use a queue to handle `relevant_planes` per data update.
    The algorithm keeps track of already tracked planes and switches the focus to planes that haven't been tracked yet.
    `RANGE` should be relatively small giving us less possible concurrent planes to handle at a time, as the more planes are in the area,
    the higher the chance some planes will not be tracked whatsoever due to the latching time.

    - v.5.0.0 improvement: the algorithm now prioritizes selecting a plane that has the highest `ApproachRate` when choosing a new focus plane with the use of
    `prioritizer()`. The `ApproachRate` value is already pre-calculated from the main `LOOP`.
    - v.8.0.0 improvement: if a plane is estimated to leave the area on the next loop, it is ignored when we need to select another focus plane.

    A built-in metric on tracking the overall selection "efficiency" is by watching the value of 'Aircraft selections' in Interactive Mode introduced in v.2.4.0.
    The value should almost always be equal to or greater than the amount of flybys over the course of a day; a value lower than flybys means that some planes
    were not tracked whatsoever (very unlikely) or that FlightGazer was recently restarted and reinitialized to the last saved flyby count (more likely).
    A much higher value (1.5x-3x) is reflective of a very active area being monitored as the rate of switching increases to accommodate for increased traffic.

    An additional metric, "plane load", was also introduced in v.9.0.0, which measures the average amount of relevant planes the selection algorithm has to choose from
    when active over a sliding window of the last 500 loop cycles. When using the default `RANGE` and `HEIGHT_LIMIT`, along with a site deemed "really really active"
    (see `runtime_accumulators_reset()`), this value has been emperically seen to hover around 1.8-2.3. If a site is sized too large for the aircraft activity in the area,
    this value will be higher than this value range and the algorithm has to switch faster to handle the traffic.
    Index 1 of `plane_load` is a measure of how long the algorithm is active on average; with the default `RANGE` and `HEIGHT_LIMIT`, a jetliner inside this zone takes about 1 minute
    and a general aviation plane takes roughly 2.5 minutes to traverse the area. Being inline with parallel runways at a busy airport this average can go up to 3-5 minutes.

## API Results Table
    API results to output table:

       --- API Result ---   |  O  |  D  |  on  |  oc  |  dn  |  dc  |  t  |  S  | --- Notes ---
    ______________________________________________________________________________________________________
    Full                    |  X  |  X  |  X   |  X   |  X   |  X   |  X  |  0  |
    Chartered/location only |  X  |     |  X   |  X   |      |      |  X  |  0  |
    Coordinate origin only  |  X  |  m  |      |  X   |      |      |  X  |  0  | O = latitude coordinate, D = longitude coordinate
    No result/blocked plane |  m  |     |      |      |      |      |     |  1  | O = "N/A"
    Non HTTP-200 result     |     |     |      |      |      |      |     |  2  |
    Any other failure       |     |     |      |      |      |      |     |  3  |

    Key:
    O  = origin airport code
    D  = destination airport code
    on = origin airport name
    oc = origin airport city/location
    dn = destination airport name
    dc = destination airport city/location
    t  = time flight took off or was first tracked
    S  = API_status value
    X  = Uses API result
    m  = Modifies/overloads the normal output

## How `synchronizer` Works
> *tl;dr do some phase synchronization and reach/maintain a form of phase-locked loop*<br>

    ------ Timing logic and what we're trying to achieve -----

    Figure 1: Time slice of key processing points

     Wall Time --->
     ░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░▒▒▒▒▓▓▓▓//▓▓▓▓
     ^       ^             ^   ^   ^        ^
     |1      |2            |3  |4  |5*      |6

    Key:
        1   = Position data of plane (`seen_pos` in json)
        2   = json timestamp (Unix time on the dump1090 system)
        2-3 = "The Unknowns"
              This is the "uncorrectable" time, which includes
              time mismatch between systems (the majority of this value),
              and other minutae such as jitter in the age data, time for the
              filesystem to write the file and become accessible, our own estimation errors, etc
        3   = FlightGazer starts polling
        3-4 = Data is transferred and received by FlightGazer (`process_time[0]`)
        4   = FlightGazer begins converting the data into an internal form
        4-5 = Data is processed (`process_time2[2]`)
        5   = Processing is complete
        *   = The local Unix time at this point used in the calculations
        2-5 = The json data age (`dump1090_json_age[0]`)
        6   = Time after sleeping for (LOOP_INTERVAL - various time adjustments) and we start polling
              again. (Relationally equivalent to point 3)

    Figure 2: Response curve of json data age

                 Phase 1 <-|-> Phase 2        |-> Phase 3
     ^                     |                  |
     │                     |                  |
     │       ■       ■     |                  |         --- max   ----------------------
     │      ■■      ■■     |                  |                                        |
    A│     ■ ■     ■ ■     |                  |                                        |
    G│    ■  ■    ■  ■    ■■■                 |                                        |
    E│   ■   ■   ■   ■   ■   ■■               |                                        |-- json refresh rate
     │  ■    ■  ■    ■  ■      ■■■            |                                        |
     │ ■     ■ ■     ■ ■          ■■■■■■■■■■■■■■■■■■■   --- target to achieve          |
    s│■      ■■      ■■                                     synchrony                  |
    e│       ■       ■                                  --- min   ----------------------
    c│                                                                                 |-- "The Unknowns" offset
     |                                                                                 |
     │░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   --- Avg processing time     ----
     │░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░       (duration 3-5 in Figure 1)
     └────────────────────────────────────────────────> --- Baseline
                         Wall Time

    Notes:
    - Jumping from min to max (and vice versa) is referred to as "wrapping around" internally
    - The algorithm to derive the target age is described in the `adjust_target()` function
    - The target age can change over time due to drift when connected to another system;
      the algorithm to determine when to change the target age is described in `drift_watcher()`
    - This whole class is very robust when the json and this program are running on the same system.
      It's when there are two systems involved that we run into complications, mainly just determining
      "The Unknowns" offset as drift occurs and clocks change, etc, and recalculating a new target point.
      As long as the target age is achievable, this setup works very well to keep things locked in phase.
        - If the time offset is negative (eg the remote system has an advanced clock and timestamps are in the future)
        then gg (there are some workarounds elsewhere in this program that attempts to handle this situation but realistically
        it's not *that* big of a deal in the grand scheme of things, we basically just ignore it and focus on keeping drift in check)

## The `Display` Class
> *Uses techniques from Colin Waddell's its-a-plane-python project but diverges significantly from his design.*

    This Display class is a huge mess, but it works and its structure has not changed since v.0.8.0.
    On a Raspberry Pi Zero 2W and using rgbmatrix, it takes about 4 ms to generate each frame.
    Why is this class not broken out as its own module? Threading and global variables, basically. A rewrite at this point isn't worth it imho.
    Data to display is handled and parsed by `DisplayFeeder` while time-based elements like the clock are handled internally.
    Actual draw routines and shape primitives are also handled internally.

    Drawing to the display is done in parts and containerized by functionality; as individual data samples can change from loop to loop, it's more
    "efficient" and flexible to handle the drawing elements piecewise rather than as a whole "scene". This does make the overall logic handling harder,
    as at this point (v.8.1.0) there are 7 settings that influence the rendering of 4 main layouts, each with subvariations which rely on logic agreements between methods.
    Additionally during runtime, these layouts can switch between one another as required by other global runtime variables referenced outside of this class.
    Keeping track of how globals influence what each method does is one of the main sticking points in regards to adding or modifying the display layout.
    But realistically, the layout has been stable with the last major addition being v.6.0.0 and nothing in the forseeable future should change this in a significant way.
    (see the changelog of this class at the end of this docstring, I hope you like reading lore)

    Figure 1: The general display state flowchart

    ░░░░░░░░░░░░░░░░░                  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
    ░   Clock (2)   ░ ◄──────────────► ░   Active Plane Display                                        ░
    ░░░░░░░░░░░░░░░░░                  ░            |                                                  ░
    Base Display Layout                ░            if        F ──► Default Journey -or (3)-           ░
                                       ░     ENHANCED_READOUT       Journey Plus (1)                   ░
                                       ░            |                  ▲                               ░
                                       ░           T|                  | depends on                    ░
                                       ░            |                  | ENHANCED_READOUT_AS_FALLBACK  ░
                                       ░            |                  ▼                               ░
                                       ░            └───────────► Enhanced Readout (1)                 ░
                                       ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

    Key:
    Sublayouts that are chosen on startup:
        (1) The default layout or when SHOW_EVEN_MORE_INFO is enabled
        (2) The default or when CLOCK_CENTER_ROW_2ROWS is enabled
        (3) Default Journey or Journey Plus

    Notes:
    Essentially at every loop, all methods are called to draw to the display, but their ability to draw is mainly controlled
    by the global `active_plane_display`. Then, each section will draw their respective part, depending on what needs to be drawn
    and where, including positioning, what font to use, and what color. Look through each method as needed.

    Use the @Animator decorator to control both how often elements update along with associated logic evaluations.
    When using the decorator, the second (optional) argument specifies the offset for each element in the render queue such that
    when (global frame counter - offset) % frame duration == 0, the method will run (except for the first frame).
    Additional quirks: methods when requested to render on the same frame as another are rendered alphabetically, not
    in the order they are defined in the class. Hence why methods within this class will have a letter prefix before their name.
    Additionally, each method has their own internal frame counter `count` for each time they are run, incremented by `Animator`.
    If a method returns True, this resets that internal counter.

    Figure 2: Frame representation in relation to method order and arguments

    Frame ---->  0      1      2      3      4 ...
    a_func(1)    ░░░0░░░▒▒▒1▒▒▒░░░2░░░▒▒▒3▒▒▒
    ab_func(2,1) ░░░░░░░0░░░░░░▒▒▒▒▒▒▒1▒▒▒▒▒▒
    b_func(1)    ░░░0░░░▒▒▒1▒▒▒░░░2░░░▒▒▒3▒▒▒
    c_func(3,1)         ░░░░░░░░░░0░░░░░░░░░░
    ...

    Major additions/changes to this class (living document):
    - v.9.6.0: Add support for weather information
    - v.8.2.1: More "flexible" attribute setting
    - v.8.2.0: Add support for additional rgbmatrix options for different setups
    - v.8.1.0: In JOURNEY_PLUS and with SHOW_EVEN_MORE_INFO, the Time/RSSI section now shows ground track instead
    - v.8.0.0: Add variable/adaptive frame rate
    - v.6.0.0: Implemented the scrolling/marquee (SHOW_EVEN_MORE_INFO), requiring font adapations and layout changes for ENHANCED_READOUT and JOURNEY_PLUS
    - v.3.4.0: Fully enable JOURNEY_PLUS
    - v.3.3.0: Responsiveness improvements
    - v.3.1.0: Add handling for ALTERNATIVE_FONT
    - v.3.0.0:
        - Depreciate old sunrise/sunset method and use CLOCK_CENTER_ROW
        - Enable printing of two lines in the Clock's center row
    - v.2.9.0:
        - Add progress bar for planes
        - Add exception handling for this class
    - v.2.2.0: Colors are no longer hardcoded
    - v.2.1.0: Rewrote callsign blink routine
    - v.2.0.0:
        - Add sunrise/sunset times or receiver stats to clock
        - Add brightness changing
        - Add callsign blinking
    - v.1.4.0: Introduced ENHANCED_READOUT
    - v.1.0.0: Baseline Release - "works good enough"
    - v.0.9.0: The Clock works
    - v.0.8.0: Borrow logic framework from Collin Waddell's `its-a-plane` project and lay groundwork for this class