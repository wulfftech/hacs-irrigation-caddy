DOMAIN = "irrigation_caddy"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_ZONE_DURATION = 10  # minutes

MAX_ZONES = 9
MAX_PROGRAMS = 3

# The firmware exposes manual watering as a pseudo-program numbered
# maxProgs + 1. It appears as pgmNum=4 on POSTs, progNumber=4 in status.json,
# and progNumber:'Run Now' in js/indexVarsDyn.js?program=4.
RUN_NOW_PROGRAM = MAX_PROGRAMS + 1

CONF_HOST = "host"
CONF_PORT = "port"
CONF_ZONE_DURATION = "zone_duration"          # int minutes — fallback for every zone
CONF_ZONE_DURATIONS = "zone_durations"        # {"<zone>": minutes} — per-zone overrides

# The controller needs a moment after a run/stop POST before status.json
# reflects it, so each command schedules a second refresh this far out.
COMMAND_SETTLE_SECONDS = 4

# How long a zone switch may show its commanded state before the device's own
# reading wins. Bounds how long a failed command can look like it worked.
OPTIMISTIC_TIMEOUT_SECONDS = 30

# API endpoints
ENDPOINT_STATUS = "/status.json"
ENDPOINT_ZONE_NAMES = "/zoneNames.json"
ENDPOINT_PROGRAM_DATA = "/programData.json"
ENDPOINT_SETTINGS = "/settingsVars.json"
ENDPOINT_RUN_PROGRAM = "/runProgram.htm"
ENDPOINT_RUN_SPRINKLERS = "/runSprinklers.htm"
ENDPOINT_STOP_SPRINKLERS = "/stopSprinklers.htm"
ENDPOINT_SAVE_PROGRAM = "/program.htm"  # form action for schedules and Run Now (pgmNum=4)
# Per-program view variables. Requires ?program=N — see coordinator._get_program_vars.
ENDPOINT_PROGRAM_VARS = "/js/indexVarsDyn.js"
