# FLOWERBOT

Python version 2.7 and above (not supported for python3 as of 07/2019).

### Modules:
- [pytwitcherapi](https://pytwitcherapi.readthedocs.io/en/latest/userdoc/requests.html#api-requests)
- [python-twitch-irc](https://pypi.org/project/python-twitch-irc)
- [playsound](https://pythonbasics.org/python-play-sound/)
- [MySQLdb](http://mysql-python.sourceforge.net/MySQLdb.html)

### Properties:
Required channel properties:
```
bot.username= # username for bot (either your own twitch account or a separate *valid* twitch account set up specifically for your bot)
channel.name= # your twitch channel name
client_id= # your twitch client id
client_secrets= # your twitch client secrets
server.url=irc.chat.twitch.tv # default server domain
server.port=6667 # default server port to connect irc client to
```

Database properties if custom loyalty point system is desired:
```
db.host=
db.db_name=
db.user=
db.password=
db.port=
```

Additional (optional) properties:
```
channel.trused_users_list= # comma-delimited list of trusted users permitted to use mod-level commands
auto_shoutout_users_file= # path to filename containing line-delimited list of approved twitch users to give an auto shoutout to
custom_shoutouts_file= # path to tab-delimited file containing custom user shoutout messages for certain users
hype.message= # custom hype message for !hype command
ignored_users_list= # comma-delimited list of users to ignore when giving an auto shoutout or any streamer shout out (i.e., nightbot or streamelements)
restricted_users_list = # comma-delimited list of users with restricted access to command usage
queue_names_list= # comma-delimited list of queues that users can join
custom.user_shoutout_message = # auto shoutout user message template. Add ${username} to auto-insert username and ${lastgameplayed} to auto-insert user's last game played
```

Flowerbot customization and additional documentation:
- [Custom Queues](./docs/Queues.md)

### Usage:
```
python flowerbot.py --properties-file /path/to/properties/file
```

### Compile:
Compile flowerbot to launch from script or streamdeck with a python launcher.

First add `FLOWERBOT_HOME=/path/to/flowerbot` to your automation environemnt (i.e., ~/.bashrc).

Then compile `launchbot.py`:
```
python -m py_compile scripts/launchbot.py
```

Confirm that when the `launchbot` application is run that the correct version of Python launcher is running the app (i.e., not Python 3 launcher). The default launcher can be set for `*.pyc` file types by right clicking the compiled file and selecting "Get Info". From the pop up menu, change the default application for opening this type of file. (Note: These instructions are for configuring the default launcher if using a Mac.)
