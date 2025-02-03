import sys
import os
from pathlib import Path
from configparser import ConfigParser
from dotenv import load_dotenv

config = None

load_dotenv()


def load_config(config_abs):
    global config

    if not os.path.exists(config_abs):
        print(f"Could not find config file: {config_abs}")
        sys.exit(1)

    config = ConfigParser()
    config.read(config_abs)

    assert list(config.keys()) == ['DEFAULT', 'server', 'deezer'], f"Validating config file failed. Check {config_abs}"

    if "DEEZER_COOKIE_ARL" in os.environ.keys() and len(os.environ["DEEZER_COOKIE_ARL"].strip())>0:
        config["deezer"]["cookie_arl"] = os.environ["DEEZER_COOKIE_ARL"]

    if len(config["deezer"]["cookie_arl"].strip()) == 0:
        print("ERROR: cookie_arl must not be empty")
        raise Exception("DEEZER_COOKIE_ARL environment variable not set.")
    print(f"ARL: {config['deezer']['cookie_arl']}")
    
    return(config)