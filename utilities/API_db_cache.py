""" Module that handles the persistent API results cache. """
""" Derived from the original `database_lookup.py` module. """
import sqlite3
from pathlib import Path
from time import perf_counter, time
import logging
from collections import deque

database_logger = logging.getLogger("API-cache-handler")

class APICacheHandler:
    """ Handles the database querying. Pass a path for the database location,
    a timeout in seconds, and an entry staleness limiter in days.
    Once this class is instantiated, use `.connect()` to initiate the database connection. Don't forget
    to call `.close()` at some point! (preferably during shutdown) """
    def __init__(self, database_location, timeout: float=1, stale: int=30):
        self.database_path = Path(database_location).as_posix()
        self.queries = 0
        self.query_misses = 0
        self.hits = 0
        self.errors = 0
        self.commits = 0
        self.last_access_speed = 0.0 # ms
        self._timeout = timeout * 0.25
        self._connection = None
        self._access_times = deque(maxlen=50)
        self.average_speed = 0.0
        self.stale_age = stale * 86400 # seconds

    def connect(self) -> bool:
        """ Connect to the database that was provided when this class was instanced.
        Returns `False` if the database fails to connect, `True` otherwise (includes when trying to establish a new connection with
        a currently existing connection). """
        if self._connection is not None:
            database_logger.warning(f"{self.database_path} is already connected! Only one connection is allowed at a time.")
            return True
        else:
            try:
                database_logger.debug(f"SQLite ver {sqlite3.sqlite_version}")
                if not Path(self.database_path).is_file():
                    database_logger.info(f"API cache could not be found, creating new database at {self.database_path}")
                else:
                    database_logger.debug(f"Found {self.database_path}")
                self._connection = sqlite3.connect(f"file:{self.database_path}", uri=True, timeout=self._timeout, check_same_thread=False)
                cursor = self._connection.cursor()
                self._connection.row_factory = sqlite3.Row
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS results (
                    Flight TEXT PRIMARY KEY,
                    Identity TEXT,
                    Origin TEXT,
                    OriginICAO TEXT,
                    OriginName TEXT,
                    OriginCity TEXT,
                    Destination TEXT,
                    DestinationICAO TEXT,
                    DestinationName TEXT,
                    DestinationCity TEXT,
                    Time INTEGER
                    );
                """)
                linecount: tuple = self._connection.execute("SELECT COUNT(*) FROM results;").fetchone()
                database_logger.info(f"Amount of entries in database: {linecount[0]}")
                cursor.close()
                # reset the stats upon connection
                self.queries = 0
                self.query_misses = 0
                self.errors = 0
                self.last_access_speed = 0.0
                self._access_times.clear()
                self.average_speed = 0.0
                self.hits = 0
                return True

            except sqlite3.Error as e:
                database_logger.exception(f"{e}")
                self._connection = None
                return False

    def fetch(self, flight: str) -> dict | None:
        """ Fetch the associated database row given a Flight. Returns `None` if no result or the database isn't connected yet.
        Valid keys in returned dict are:
        `Flight`, `Identity`, `Origin` `OriginICAO`, `OriginName`, `OriginCity`, `Destination`, `DestinationICAO`, `DestinationName`, `DestinationCity`.
        If there is a successful hit, increments the `queries` and `hit` attributes.
        If there are any errors or an attempt to access with no connection, increments only `errors`.
        If there is no result, increments both `query_misses` and `queries`. """
        result = None
        if self._connection is not None:
            try:
                start = perf_counter()
                # match the callsign; usually works
                cursor = self._connection.execute(
                    f"SELECT * FROM results WHERE Flight = ? AND time > strftime('%s', 'now') - ?;",
                    (flight, self.stale_age)
                )
                # try and see if we can match what the API reported
                if not (result := cursor.fetchone()):
                    # in case of matching flights, use the latest one
                    cursor = self._connection.execute(
                        f"SELECT * FROM results WHERE Identity = ? AND time > strftime('%s', 'now') - ? ORDER BY time DESC;",
                        (flight, self.stale_age)
                    )
                    result = cursor.fetchone()
                cursor.close()
                self.last_access_speed = (perf_counter() - start) * 1000
                self._access_times.appendleft(self.last_access_speed)
                self.average_speed = sum(self._access_times) / len(self._access_times)
                self.queries += 1
            except sqlite3.Error as e:
                database_logger.exception(f"{e}")
                self.errors += 1
        else:
            database_logger.debug("Attempt to query database with no connection.")
            self.errors += 1
            return None

        if result:
            database_logger.debug(f"Database hit for \'{flight}\', lookup took {self.last_access_speed:.3f} ms")
            self.hits += 1
            return dict(result)
        else:
            # database_logger.debug(f"Could not find database entry for \'{flight}\'")
            self.query_misses += 1
            return None

    def append(self, data: dict) -> None:
        """ Add new data to this database. """
        flight = data.get('Flight')
        type = data.get('Type')
        if not flight:
            database_logger.warning("Did not receive a valid API result.")
            return
        if type != "Airline":
            database_logger.debug(f"Not appending \'{flight}\' as it is not a commercial flight.")
            return
        if (destination := data.get('Destination')) is None:
            database_logger.debug(f"Not appending \'{flight}\' as it has no destination data.")
            return

        # unpack the API result
        identity = data.get('Identity')
        origin = data.get('Origin')
        origin_icao = data.get('OriginICAO')
        destination_icao = data.get('DestinationICAO')
        origin_name = data.get('OriginInfo')[0]
        origin_city = data.get('OriginInfo')[1]
        destination_name = data.get('DestinationInfo')[0]
        destination_city = data.get('DestinationInfo')[1]
        time_now = time()

        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO results (
                    Flight,
                    Identity,
                    Origin,
                    OriginICAO,
                    OriginName,
                    OriginCity,
                    Destination,
                    DestinationICAO,
                    DestinationName,
                    DestinationCity,
                    Time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(Flight) DO UPDATE SET
                    Identity=excluded.Identity,
                    Origin=excluded.Origin,
                    OriginICAO=excluded.OriginICAO,
                    OriginName=excluded.OriginName,
                    OriginCity=excluded.OriginCity,
                    Destination=excluded.Destination,
                    DestinationICAO=excluded.DestinationICAO,
                    DestinationName=excluded.DestinationName,
                    DestinationCity=excluded.DestinationCity,
                    Time=excluded.Time;
                """,
                (
                    flight,
                    identity,
                    origin,
                    origin_icao,
                    origin_name,
                    origin_city,
                    destination,
                    destination_icao,
                    destination_name,
                    destination_city,
                    time_now
                )
            )
            self._connection.commit()
            cursor.close()
            database_logger.debug(f"Successfully added entry for \'{flight}\'")
            self.commits += 1

        except sqlite3.Error as e:
            database_logger.exception(f"Could not commit to database: {e}")
            self.errors += 1
            return

    def prune(self) -> None:
        """ Prune old entries from the database. """
        if self._connection is None:
            database_logger.warning("Attempt to prune database with no connection.")
            return

        database_logger.debug(f"Pruning database for entries older than {self.stale_age} days...")
        cursor = self._connection.cursor()
        try:
            linecount_start = self._connection.execute("SELECT COUNT(*) FROM results;").fetchone()
            cursor.execute(
                f"""
                DELETE FROM results
                WHERE Time < strftime('%s', 'now') - {self.stale_age};
                """
            )
            self._connection.commit()
            linecount_end = self._connection.execute("SELECT COUNT(*) FROM results;").fetchone()
            database_logger.debug(f"Pruned {linecount_start[0] - linecount_end[0]} entries; "
                                f"database now has {linecount_end[0]} entries.")
            cursor.close()
        except sqlite3.Error as e:
            database_logger.exception(f"Failed to prune database: {e}")
            self.errors += 1
            return

        self.commits += 1

    def is_connected(self) -> bool:
        """ Check if we are connected to the database. """
        if self._connection is not None:
            return True
        else:
            return False

    def close(self) -> None:
        """ Close the connection. """
        if self._connection is not None:
            self._connection.close()
            database_logger.debug("Database successfully closed.")
            self._connection = None
        else:
            database_logger.warning("Attempt to close database with no established connection.")