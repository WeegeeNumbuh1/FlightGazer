# Script that checks if the FlightGazer virtual environment is valid.
# If the required modules can't be loaded, this will return an exit code of 1.
# This script assumes it's being run by the FlightGazer-init.sh script.
# Last updated: v.8.4.0
# By: WeegeeNumbuh1
import sys
try:
    import ruamel.yaml
    import requests
    from pydispatch import dispatcher
    import schedule
    import psutil
    import suntime
except Exception:
    sys.exit(1)
sys.exit(0)