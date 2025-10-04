""" Module that handles all the database querying on behalf of FlightGazer. """
import sqlite3
from pathlib import Path
from time import perf_counter
import logging
from collections import deque

database_logger = logging.getLogger("database-handler")

class DatabaseHandler:
    """ Handles the database querying. Pass a path for the database location and a timeout in seconds.
    Once this class is instantiated, use `.connect()` to initiate the database connection. Don't forget
    to call `.close()` at some point! (preferably during shutdown) """
    def __init__(self, database_location, timeout: float):
        self.database_path = Path(database_location).as_posix()
        self.queries = 0
        self.query_misses = 0
        self.query_errors = 0
        self.last_access_speed = 0.0 # ms
        self._timeout = timeout * 0.25
        self._connection = None
        self._access_times = deque(maxlen=50)
        self.average_speed = 0.0
        self.database_version = ''

    def connect(self) -> bool:
        """ Connect to the database that was provided when this class was instanced.
        Opens the database as read-only.
        Returns `False` if the database fails to connect, `True` otherwise (includes when trying to establish a new connection with
        a currently existing connection). """
        if self._connection is not None:
            database_logger.warning(f"{self.database_path} is already connected! Only one connection is allowed at a time.")
            return True
        else:
            try:
                database_logger.debug(f"SQLite ver {sqlite3.sqlite_version}")
                self._connection = sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True, timeout=self._timeout, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
                cursor = self._connection.execute("SELECT * FROM DB_INFO ORDER BY ROWID ASC LIMIT 1")
                result = cursor.fetchone()
                cursor.close()
                if result is not None:
                    result = dict(result)
                    database_logger.info("Connected to database. "
                                         f"Version: {result['version']}, "
                                         f"created on: {result['created_date']}"
                                         )
                else:
                    raise KeyError
                return True
            except sqlite3.Error as e:
                database_logger.error(f"{e}")
                self._connection = None
                return False
            except KeyError:
                database_logger.error("Could not determine database information. This database may not be valid. Terminating connection.")
                self._connection.close()
                self._connection = None
                return False

    def fetch(self, icao: str) -> dict | None:
        """ Fetch the associated database row given an ICAO. Returns `None` if no result or the database isn't connected yet.
        Valid keys in returned dict are `icao`, `reg`, `type`, `flags`, `desc`, `year`, `ownop`.
        If there is a successful hit, increments the `queries` attribute. If there are any errors or an attempt to access with no
        connection, increments `query_errors`. If there is no result, increments both `query_misses` and `queries`. """
        result = None
        if self._connection is not None:
            try:
                start = perf_counter()
                cursor = self._connection.execute(f"SELECT * FROM ICAO_{icao[0]} WHERE icao = ?", (icao.upper(),))
                result = cursor.fetchone()
                cursor.close()
                self.last_access_speed = (perf_counter() - start) * 1000
                self._access_times.appendleft(self.last_access_speed)
                self.average_speed = sum(self._access_times) / len(self._access_times)
                self.queries += 1
            except sqlite3.Error as e:
                database_logger.error(f"{e}")
                self.query_errors += 1
        else:
            database_logger.debug("Attempt to query database with no connection.")
            self.query_errors += 1
            return None
        if result:
            # database_logger.debug(f"Database hit for {icao}, lookup took {self.last_access_speed:.3f} ms")
            return dict(result)
        else:
            database_logger.info(f"Rare event! Could not find database entry for \'{icao}\'")
            self.query_misses += 1
            return None

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