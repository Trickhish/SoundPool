import sys
import os
from pathlib import Path
from configparser import ConfigParser
from dotenv import load_dotenv

config = None

load_dotenv()

class ConfigError(Exception):
    def __init__(self, message):            
        super().__init__(message)

def load_config(config_abs):
    global config

    if not os.path.exists(config_abs):
        raise ConfigError(f"Could not find config file: {config_abs}")
        #print(f"Could not find config file: {config_abs}")
        #sys.exit(1)

    config = ConfigParser(interpolation=None)
    config.read(config_abs)

    #assert list(config.keys()) == ['DEFAULT', 'server', 'database', 'deezer'], f"Validating config file failed. Check {config_abs}"
    cfk = list(config.keys())
    expk = ['server', 'database', 'deezer']
    for k in expk:
        if not k in cfk:
            raise ConfigError(f"The '{k}' category was not found in {config_abs}")

    if "SP_DEEZER_ARL" in os.environ.keys() and len(os.environ["SP_DEEZER_ARL"].strip())>0:
        config["deezer"]["cookie_arl"] = os.environ["SP_DEEZER_ARL"]

    if len(config["deezer"]["cookie_arl"].strip()) == 0:
        print("ERROR: cookie_arl must not be empty")
        raise ConfigError("SP_DEEZER_ARL environment variable not set.")
    if config["server"]["debug"].lower().strip()=="true":
        config["server"]["debug"]="true"
        #print(f"ARL: {config['deezer']['cookie_arl']}\n")


    if (len(config["server"]["token_expiry_hours"].strip())==0 or int(config["server"]["token_expiry_hours"]) < 1):
        config["server"]["token_expiry_hours"] = "24"

    
    if not "SP_JWT_SECRET_KEY" in os.environ.keys():
        raise Exception("SP_JWT_SECRET_KEY environment variable is required.")
    config["server"]["jwt_secret_key"] = os.environ["SP_JWT_SECRET_KEY"]

        
    return(config)

if config==None:
    config = load_config("cs_config.ini")