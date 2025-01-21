# Settings migration script for FlightGazer
# Designed for use with versions >= 2.0.0
# Only designed to be used by the updater script "update.sh"
# Usage outside of that environment can lead to unexpected results.
# Last updated: v.2.1.0
# By WeegeeNumbuh1

import sys
if __name__ != '__main__':
    print("This file cannot be loaded as a module.")
    sys.exit(1)
import argparse
import os
from pathlib import Path
os.environ["PYTHONUNBUFFERED"] = "1"
# we need this for programmatic, round-trip updating. It should already be in the venv for use
try:
    from ruamel.yaml import YAML
except:
    print(f"Error: Migrator failed to load required module \'ruamel.yaml\'. Is it present in the venv?")
    sys.exit(1) 

parser = argparse.ArgumentParser()
parser.add_argument("current_settings_file")
parser.add_argument("new_settings_file")
args = parser.parse_args()

PATH1 = Path(args.current_settings_file)
PATH2 = Path(args.new_settings_file)

print(f"Current configuration file: {PATH1}\nNew configuration file:     {PATH2}")

yaml=YAML()

try:
    user_settings = yaml.load(open(PATH1, 'r'))
except:
    print(f"Error: Could not load config file \'{PATH1}\'.")
    sys.exit(1)
try:
    new_config = yaml.load(open(PATH2, 'r'))
except:
    print(f"Error: Could not load config file \'{PATH2}\'.")
    sys.exit(1)
try:
    old_version = user_settings['CONFIG_VERSION']
    new_version = new_config['CONFIG_VERSION']
except:
    print("Error: Could not read configuration version. Is this a valid FlightGazer configuration file?")
    sys.exit(1)

print("Checking configuration versions:")
if old_version == new_version:
    print("Config versions are the same.")
else:
    print(f"Migrating {old_version} -> {new_version}")

# start the comparison
print("Modifying provided config from latest build to match current settings...")
for settings_key in new_config:
    try:
        # write value of associated user setting with setting that is present in the new config
        # if there are settings that have been removed in the newer config, this will
        # never read them anyway
        if settings_key == "CONFIG_VERSION": continue
        if new_config[settings_key] != user_settings[settings_key]:
            if settings_key == "API_KEY" and user_settings['API_KEY']:
                print(f"Changing {settings_key}: {new_config[settings_key]} -> <provided key>")
            else:
                print(f"Changing {settings_key}: {new_config[settings_key]} -> {user_settings[settings_key]}")
            new_config[settings_key] = user_settings[settings_key]
    except KeyError: # settings key in new config does not exist in the older config
        print(f"New setting in this configuration: {settings_key}")
else:
    print("All other settings are the same as the default settings.")

try:
    with open(PATH2, 'w') as updated_config:
        yaml.dump(new_config, updated_config)
except:
    print(f"Error: Could not write updated configuration file.")
    sys.exit(1)
else:
    print(f"Setting migration completed.\n")

sys.exit(0)