DOMAIN = "irrigation_caddy"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_ZONE_DURATION = 10  # minutes

MAX_ZONES = 9
MAX_PROGRAMS = 3

CONF_HOST = "host"
CONF_PORT = "port"
CONF_ZONE_DURATION = "zone_duration"
CONF_ZONE_NAMES = "zone_names"

# API endpoints
ENDPOINT_STATUS = "/status.json"
ENDPOINT_ZONE_NAMES = "/zoneNames.json"
ENDPOINT_PROGRAM_DATA = "/programData.json"
ENDPOINT_SETTINGS = "/settingsVars.json"
ENDPOINT_RUN_PROGRAM = "/runProgram.htm"
ENDPOINT_RUN_SPRINKLERS = "/runSprinklers.htm"
ENDPOINT_STOP_SPRINKLERS = "/stopSprinklers.htm"
ENDPOINT_SAVE_PROGRAM = "/saveProgram.htm"  # used for Run Now (pgmNum=4) with per-zone durations

UDP_DISCOVERY_PORT = 30303
UDP_DISCOVERY_MESSAGE = "Discovery: Who is out there?"
