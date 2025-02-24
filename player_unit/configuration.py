import sys
import os
from pathlib import Path
from configparser import ConfigParser
import socket
config = None


def load_config(config_abs):
    global config

    if not os.path.exists(config_abs):
        print(f"Could not find config file: {config_abs}")
        sys.exit(1)

    config = ConfigParser()
    config.read(config_abs)

    assert list(config.keys()) == ['DEFAULT', 'player_unit', 'server', 'download_dirs'], f"Validating config file failed. Check {config_abs}"

    if not config["player_unit"]["name"]:
        config["player_unit"]["name"] = f"soundpool.unit.{socket.gethostname()}"

    return(config)

def write_config(cfg, config_path):
    with open(config_path, "w") as f:
        config.write(f)