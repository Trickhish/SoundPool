<div align="center">
  <img style="height:180px;" src="https://github.com/Trickhish/SoundPool/blob/main/soundpool.png?raw=true" />
</div>


<h1 align="center">SoundPool</h1>
<p align="center">
  An app that allows the creation of a music pool where people can add/vote for songs to be played <br/><br/>
  <b>Thanks to <a target="_blank" href="https://github.com/kmille">@Kmille</a> for <a target="_blank" href="https://github.com/kmille/deezer-downloader">deezer-downloader</a></b>
</p>


<br/>
SoundPool works with three components: 

- The `central server` hosts the API, handles the player units and acts as an intermediary between the player units and the clients. It needs to be accessible from the clients and from the players.
- The `player units` are the one that actually play the music.
- The `website` allows the clients to interact with the players and control the music.

## Installation
### Central Server
To install the central server
```bash
git clone https://github.com/Trickhish/SoundPool
cd SoundPool/central_server
pip install -r requirements.txt
python install.py
```
By default, the port `21623` will be used and only the local host will be authorized. \
The settings can be changed in `cs_config.ini`

### Player Unit
To install the central server
```bash
git clone https://github.com/Trickhish/SoundPool
cd SoundPool/player_unit
pip install -r requirements.txt
python install.py
```

### Website
The website is a normal angular website. \
\
You can download a pre-built version from the [releases section](https://github.com/Trickhish/SoundPool/releases). \
If you do that, the website will be configured with `http://localhost:21623` as API url.\
\
You can also edit the **apiUrl** variable in `client/soundpool/src/app/api.service.ts` and build it yourself with `ng build --prod` \
or use the installation script that will set the API url from the parameter: 
```bash
node install.js <api_url>
# ex: node install.js http://localhost:21623
```

## Running
### Central Server
The central server uses the [FastAPI](https://github.com/fastapi/fastapi) python library. \
It can be launched by just running the `server.py` script. \
Or using the uvicorn command: `uvicorn server:app --host 0.0.0.0 --port 21623 --workers 4`\
\
For a production environment, it's important to pass `debug` to `false` in the configuration file. \
It is also recommended to restrict the traffic outstide of the local network by passing `host` to `localhost` and to use a proxy with HTTPS configured.\
\
A good practice for background scripts that need to run reliably is to create a [systemd service](https://linuxconfig.org/how-to-write-a-simple-systemd-service).

### Player Unit
The player can just be run as any python script. \
Like the `Central Server`, it is advised to create a service to automate the start, auto restart and facilitate the logs analysis.\
\
By default, the unit will use `localhost:21623` as the server url.

### Website
Once the static website is built, you can use any HTTP server to make it accessible (apache, nginx, caddy...).\
For the angular routing to work, it may be necessary to setup [`URL rewriting`](). \
For apache, you can follow [this article](https://dev.to/timetc/angular-with-clean-urls-using-apaches-modrewrite-2bjb).

## Dependencies
### Linux
The `libasound2-dev` package is required

### Windows
[`ffmpeg`](https://ffmpeg.org/download.html#build-windows) is required as well as [`C++ Build Tools`](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
