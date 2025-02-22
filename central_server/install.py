import configparser
import os
import random

CONFIG_FILE = "config.ini"
ENV_FILE = ".env"

def get_inputf(prompt, default):
    try:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    except:
        exit()

def get_input(prompt, default, choices=None, show_choices=True):
    try:
        while True:
            user_input = input(f"{prompt} {('['+default+']') if (not choices or not show_choices) else ('['+("/".join(map(str, choices)))+']')}: ").strip()

            if not user_input:
                return default

            if choices and user_input not in choices:
                print(f"❌ Invalid choice. Please select one of: {', '.join(choices)}")
            else:
                return user_input
    except:
        exit()
    

def setup_database():
    print("\n🔧 Database Configuration")

    # Select database engine
    db_engines = {
        "1": "sqlite",
        "2": "mysql",
        "3": "postgresql",
        "4": "mariadb"
    }
    
    print("\nSelect a database engine:")
    for key, value in db_engines.items():
        print(f"  {key}. {value}")

    choice = get_input("Enter choice", "1", ["1","2","3"], False)
    db_engine = db_engines.get(choice, "sqlite")

    if db_engine == "sqlite":
        db_name = get_input("Enter SQLite database filename", "music_rooms.db")
        db_url = f"sqlite:///{db_name}"
        ol=[db_engine, db_name]
    else:
        db_user = get_input("Enter database username", "root")
        db_pass = get_input("Enter database password", "password")
        db_host = get_input("Enter database host", "localhost")
        db_port = get_input("Enter database port", "3306" if db_engine == "mysql" else "5432")
        db_name = get_input("Enter database name", "music_db")

        db_url = f"{db_engine}+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}" if db_engine == "mysql" \
            else f"{db_engine}+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

        ol=[db_engine, db_user, db_pass, db_host, db_port, db_name]
    #print(f"\n✅ Database URL: {db_url}")

    return(ol)

def setup_server():
    print("\n🌍 Server Configuration")
    host = get_input("Enter server host", "0.0.0.0")
    port = get_input("Enter server port", "8000")
    debug = get_input("Enable debug mode? (yes/no)", "yes").lower() in ["yes", "y"]

    return host, port, debug

def setup_security():
    print("\n🔐 Security Configuration")

    jwt_secret = get_input("Enter JWT secret key", "Generate randomly")
    if (jwt_secret=="Generate randomly"):
        chl = "abcdefghijklmnopqrstuvwxyz"
        chl+=chl.upper()
        chl+="0123456789%*$@&#~°=+"
        jwt_secret = ("".join([random.choice(chl) for _ in range(50)]))
    
    jwt_algorithm = get_input("Enter JWT algorithm", "HS256", ["HS256", "RS256", "ES256"])
    token_expiry = get_input("Enter token expiry (hours)", "24")

    return jwt_secret, jwt_algorithm, token_expiry

def write_config(db_url, host, port, debug, jwt_algorithm, token_expiry):
    
    config = configparser.ConfigParser()
    
    config["database"] = {
        "url": db_url
    }

    config["server"] = {
        "host": host,
        "port": port,
        "debug": str(debug),
        "token_expiry_hours": token_expiry
    }

    config["security"] = {
        "jwt_algorithm": jwt_algorithm
    }

    with open(CONFIG_FILE, "w") as configfile:
        config.write(configfile)

    print(f"\n📁 Configuration saved to {CONFIG_FILE}")

def write_env(chkey, chvalue):
    env_vars = {}

    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as envfile:
            for line in envfile:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()

    env_vars[chkey] = chvalue

    with open(ENV_FILE, "w") as envfile:
        for key, value in env_vars.items():
            envfile.write(f"{key}={value}\n")

    print(f"🔑 {chkey} updated in {ENV_FILE}")


def main():
    print("⚙️  Welcome to the SoundPool Installer!\n")

    config = configparser.ConfigParser()

    config["database"] = {}
    dbl = setup_database()
    if (dbl[0]=="sqlite"):
        dbn=dbl[1]
        config["database"] = {
            "engine": "sqlite",
            "name": dbn
        }
    else:
        eng, dbusr, dbpass, dbhost, dbport, dbn=dbl
        config["database"] = {
            "engine": eng,
            "host": dbhost,
            "port": dbport,
            "user": dbusr,
            "name": dbn
        }
        write_env("SP_DB_PASSWORD", dbpass)
    
    host, port, debug = setup_server()
    jwt_secret, jwt_algorithm, token_expiry = setup_security()

    write_env("SP_JWT_SECRET_KEY", '"'+jwt_secret+'"')

    config["server"] = {
        "host": host,
        "port": port,
        "debug": str(debug),
        "token_expiry_hours": token_expiry
    }

    config["security"] = {
        "jwt_algorithm": jwt_algorithm
    }

    with open(CONFIG_FILE, "w") as configfile:
        config.write(configfile)

    print(f"\n📁 Configuration saved to {CONFIG_FILE}")



    print("\n🚀 Setup complete! You can now start the SoundPool server.")

if __name__ == "__main__":
    main()
