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
channel.mod_permissions_list= # comma-delimited list of users with mod permissions
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

### Usage:
```
python flowerbot.py --properties-file /path/to/properties/file --cross-talk-channels [optional, comma-delimited list of channels to share messages to]
```
