# FlightGazer service file updater
# Updates the service definition as necessary depending on the update.
# Only designed to be used by the updater script "update.sh"
# Usage outside of that environment can lead to unexpected results.
# Last updated: v.11.1.1
# By WeegeeNumbuh1

import sys
if __name__ != '__main__':
    print("This file cannot be loaded as a module.")
    sys.exit(1)
import argparse
import os
from pathlib import Path
os.environ["PYTHONUNBUFFERED"] = "1"
SERVICE_PATH = Path('/etc/systemd/system/flightgazer.service')

parser = argparse.ArgumentParser()
parser.add_argument("new_init_file")
args = parser.parse_args()

PATH1 = Path(args.new_init_file)

if not SERVICE_PATH.exists():
    print(f"Error: \'{SERVICE_PATH}\' does not exist.")
    sys.exit(1)
if not PATH1.exists():
    print(f"Error: \'{PATH1}\' does not exist.")
    sys.exit(1)

# taken from the web-app
STARTUP_OPTIONS = [
    {'name': 'No Display mode', 'flag': '-d'},
    {'name': 'Emulation mode', 'flag': '-e'},
    {'name': 'No Filter mode', 'flag': '-f'},
    {'name': 'Verbose/debug mode', 'flag': '-v'},
]

with open(SERVICE_PATH, 'r', encoding='utf-8') as f:
    serv_lines = f.readlines()
old_init_ver = None
exec_line = ''
for line in serv_lines:
    if 'SERVICE_FILE_VERSION' in line:
        try:
            old_init_ver = line.split('=')[1].strip()
        except Exception:
            pass
    if line.strip().startswith('ExecStart='):
        exec_line = line.strip()

if not exec_line:
    print("Error: could not determine startup command for service file.")
    sys.exit(1)

flags = []
for opt in STARTUP_OPTIONS:
    if f' {opt["flag"]}' in exec_line:
        flags.append(opt['name'])

if not (flags_desc := ', '.join(flags)):
    flags_desc = None
exec_path = None
# note: if the filepath isn't encapsulated in quotes,
# we're still fine because we just copy over the line,
# not the parsed version here
for exec_split in exec_line.split('"'):
    if 'FlightGazer-init.sh' in exec_split:
        exec_path = exec_split.strip()
if not exec_path:
    print("Error: Cannot find executable path in service file.")
    sys.exit(1)

with open(PATH1, 'r', encoding='utf-8') as f:
    new_init = f.readlines()

start_marker = "# SERVICE_FILE_START"
end_marker = "# SERVICE_FILE_END"
start_index = None
end_index = None
for i, line in enumerate(new_init):
    if start_marker in line:
        start_index = i
    elif end_marker in line:
        end_index = i
        break

if start_index is None or end_index is None:
    print("Error: Could not find start or end markers in the new initialization file.")
    sys.exit(1)

# get rid of the heredoc command and the EOF line
extracted = new_init[start_index + 2:end_index - 1]
formatted_new = []
new_init_ver = None
for line in extracted:
    if 'SERVICE_FILE_VERSION' in line:
        try:
            new_init_ver = line.split('=')[1].strip()
        except Exception:
            pass
    formatted_new.append(line.strip())

print(f"Startup path: \'{exec_path}\'")
print(f"Additional startup options: {flags_desc}")

if not old_init_ver and new_init_ver:
    print(f"Updating old-style service definition to version {new_init_ver}")
if old_init_ver and new_init_ver:
    if old_init_ver == new_init_ver:
        print(f'Service file definitions are the same, no need to update.')
        sys.exit(0)
    else:
        print(f'Updating service definition from {old_init_ver} to {new_init_ver}')
if not new_init_ver:
    print("Error: could not determine new service file definition.")
    print("No changes have been done to the service.")
    sys.exit(1)

for i, line in enumerate(formatted_new):
    if line.startswith('ExecStart='):
        formatted_new[i] = exec_line
        break

try:
    with open(SERVICE_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(formatted_new))
except Exception as e:
    print(f'Error: could not write updated service file. {e}')
    sys.exit(1)

print('Done.')
sys.exit(0)