#! /usr/bin/env pytho
import sys
import irc.bot
import requests
import os
import optparse
import MySQLdb

# ---------------------------------------------------------------------------------------------
# globals
OUTPUT_FILE = sys.stdout
ERROR_FILE = sys.stderr

APPROVED_STREAMERS = {}
USERS_CHECKED = set()

# ---------------------------------------------------------------------------------------------
# required properties
APPROVED_STREAMERS_FILE = 'resources/data/approved_streamers.txt'

BOT_USERNAME = 'username'
CHANNEL = 'channel'
CLIENT_ID = 'client_id'
CLIENT_SECRETS = 'client_secrets'
IRC_CHAT_SERVER_PORT = 'server.port'
IRC_CHAT_SERVER = 'server.url'

# db properties
DB_HOST = 'db.host'
DB_NAME = 'db.db_name'
DB_USER = 'db.user'
DB_PW = 'db.password'
DB_PORT = 'db.port'

DEAFULT_IRC_CHAT_SERVER = 'irc.chat.twitch.tv'
DEFAULT_CHAT_SERVER_PORT = 6667

# ---------------------------------------------------------------------------------------------
# db functions
def establish_db_connection(properties):
    ''' Establishes database connection. '''
    try:
        connection = MySQLdb.connect(host=properties[DB_HOST], port=int(properties[DB_PORT]),
                            user=properties[DB_USER],
                            passwd=properties[DB_PW],
                            db=properties[DB_NAME])
    except MySQLdb.Error, msg:
        print >> ERROR_FILE, msg
        sys.exit(2)
    return connection

class TwitchBot(irc.bot.SingleServerIRCBot):
    def __init__(self, properties_filename):
        properties = self.parse_properties(properties_filename)
        self.channel_display_name = properties[CHANNEL]
        self.channel = '#' + properties[CHANNEL]
        # self.bot_username = properties[BOT_USERNAME]
        self.client_id = properties[CLIENT_ID]
        self.token = properties[CLIENT_SECRETS]
        self.approved_streamers_file = properties.get(APPROVED_STREAMERS_FILE,'')
        self.death_count = 0
        self.channel_id = self.get_channel_id(properties[CHANNEL])
        self.db_connection = establish_db_connection(properties)

        server = properties.get(IRC_CHAT_SERVER, DEAFULT_IRC_CHAT_SERVER)
        port = properties.get(IRC_CHAT_SERVER_PORT, DEFAULT_CHAT_SERVER_PORT)

        # Create IRC bot connection
        print >> OUTPUT_FILE, 'Connecting to %s on port %s...' % (server, port) 
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, 'oauth:'+ self.token)], properties[BOT_USERNAME], properties[BOT_USERNAME])

    def parse_properties(self, properties_filename):
        ''' Parses the properties file. '''
        properties = {}
        with open(properties_filename, 'rU') as properties_file:
            for line in properties_file:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                property = map(str.strip, line.split('='))
                if len(property) != 2:
                    continue
                properties[property[0]] = property[1]

        # error check required properties
        if (CHANNEL not in properties or len(properties[CHANNEL]) == 0 or
            CLIENT_ID not in properties or len(properties[CLIENT_ID]) == 0 or
            CLIENT_SECRETS not in properties or len(properties[CLIENT_SECRETS]) == 0 or
            BOT_USERNAME not in properties or len(properties[BOT_USERNAME]) == 0):
            print >> ERROR_FILE, 'Missing one or more required properties, please check property file'
            sys.exit(2)

        # init approved streamers list for auto-shoutouts (optional)
        if os.path.exists(APPROVED_STREAMERS_FILE):
            self.init_approved_streamers(APPROVED_STREAMERS_FILE)
        return properties
    
    def init_approved_streamers(self, approved_streamers_filename):
        with open (approved_streamers_filename, 'rU') as approved_streamers_file:
            for username in approved_streamers_file.readlines():
                APPROVED_STREAMERS[username.strip()] = False

    def on_welcome(self, c, e):
        ''' Handle welcome. '''
        print >> OUTPUT_FILE, 'Joining channel: %s' % (self.channel)
        c.cap('REQ', ':twitch.tv/membership')
        c.cap('REQ', ':twitch.tv/tags')
        c.cap('REQ', ':twitch.tv/commands')
        c.join(self.channel)

    def on_pubmsg(self, c, e):
        ''' Handles message in chat. '''
        # give a streamer shoutout if viewer is in the approved streamers set
        # and streamer has not already gotten a shout out 
        # (i.e., manual shotout with !so <username> command)
        if not e.arguments[0].startswith('!'):
            self.auto_streamer_shoutout(e)
        else:
            # If a chat message starts with an exclamation point, try to run it as a command
            parsed_args = map(lambda x: str(x).lower(), e.arguments[0].split(' '))
            cmd = parsed_args[0].replace('!','')
            cmd_args = []
            if len(parsed_args) > 1:
                cmd_args = parsed_args[1:]
            print >> OUTPUT_FILE, 'Received command: %s with args: %s' % (cmd, ', '.join(cmd_args))
            self.do_command(e, cmd, cmd_args)
            return

    # ---------------------------------------------------------------------------------------------
    # FETCH CHANNEL / USER DETAILS
    def get_username(self, e):
        ''' Returns username for given event. '''
        user = [d['value'] for d in e.tags if d['key'] == 'display-name'][0]
        return user.lower()

    def get_channel_id(self, twitch_channel):
        ''' Returns the twitch channel id. '''
        url = 'https://api.twitch.tv/kraken/users?login=' + twitch_channel
        headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
        r = requests.get(url, headers=headers).json()
        return r['users'][0]['_id']

    def get_last_game_played(self, twitch_channel_id):
        ''' Returns last game played for given channel id. '''
        url = 'https://api.twitch.tv/kraken/channels/' + twitch_channel_id
        headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
        r = requests.get(url, headers=headers).json()
        return r['game']

    def get_channel_title(self, e):
        ''' Returns channel title. '''
        url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
        headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
        r = requests.get(url, headers=headers).json()
        return r['status']

    def current_death_count(self, c):
        ''' Returns current death count. '''
        message = "cornflower's current death count is %s ;___;" % (self.death_count)
        c.privmsg(self.channel, message)
        return

    def get_current_channel_viewers(twitch_channel):
        '''
            Returns map of current channel viewers organized by type.
        '''
        url = 'http://tmi.twitch.tv/group/user/' + twitch_channel + '/chatters'
        r = requests.get(url).json()
        channel_viewers = {
            'viewers': map(str, r['chatters']['viewers']),
            'moderators': map(str, r['chatters']['moderators']),
            'broadcaster': str(r['chatters']['broadcaster']),
            'vips': map(str, r['chatters']['vips'])
        }
        return channel_viewers

    # ---------------------------------------------------------------------------------------------
    # STREAMER SHOUTOUT FUNCTIONS
    def streamer_shoutout_message(self, user):
        ''' Gives a streamer shoutout in twitch chat. '''
        c = self.connection
        cid = self.get_channel_id(user)
        game = self.get_last_game_played(cid)
        message = '@%s is also a streamer! For some %s action, check them out some time at https://www.twitch.tv/%s' % (user, game, user)
        c.privmsg(self.channel, message)
        USERS_CHECKED.add(user)

    def auto_streamer_shoutout(self, e):
        ''' Gives an automated streamer shoutout. '''
        user = self.get_username(e)
        if user in USERS_CHECKED:
            return
        if user in APPROVED_STREAMERS and not APPROVED_STREAMERS[user]:
            APPROVED_STREAMERS[user] = True
            self.streamer_shoutout_message(user)
        USERS_CHECKED.add(user)
        return

    def update_approved_streamers_list(self, streamer):
        ''' Updates approved streamers list. This is only permitted for channel broadcaster. '''
        if not streamer in APPROVED_STREAMERS.keys():
            APPROVED_STREAMERS[streamer] = True
            with open(self.approved_streamers_file, 'w') as streamer_file:
                streamer_file.write('\n'.join(APPROVED_STREAMERS.keys()))

    # ---------------------------------------------------------------------------------------------
    # BOT MAIN
    def do_command(self, e, cmd, cmd_args):
        c = self.connection
        current_viewers = self.get_current_channel_viewers(self.channel_display_name)
        cmd_issuer = self.get_username(e)
        has_mod_permissions = (cmd_issuer in current_viewers['moderators'] or cmd_issuer == current_viewers['broadcaster'])

        if cmd == "game":
            game = self.get_last_game_played(self.channel_id)
            c.privmsg(self.channel, self.channel_display_name + ' is currently playing ' + game)
        # Poll the API the get the current status of the stream
        elif cmd == "title":
            title = self.get_channel_title(self.channel_id)
            c.privmsg(self.channel, self.channel_display_name + ' channel title is currently ' + title)
        elif cmd == "so":
            self.streamer_shoutout_message(cmd_args[0])
        elif cmd == 'death':
            self.current_death_count(c)
        elif cmd_issuer == current_viewers['broadcaster']:
            if cmd == "streameraddnew":
                self.update_approved_streamers_list(cmd_args[0])
        elif has_mod_permissions:
            if cmd == 'deathadd':
                self.death_count += 1
                c.privmsg(self.channel, "%s's current death count is now %s ;___;" % (self.channel_display_name, self.death_count))
            elif cmd == 'deathreset':
                self.death_count = 0
                c.privmsg(self.channel, "%s reset their current death count :P" % (self.channel_display_name))
            elif cmd == 'deathinit':
                self.death_count = int(cmd_args[0])
                c.privmsg(self.channel, "%s initialized their current death count to %s" % (self.channel_display_name, self.death_count))

def usage(parser):
    print >> OUTPUT_FILE, parser.print_help()
    sys.exit(2)

def main():
    # parse command line
    parser = optparse.OptionParser()
    parser.add_option('-p', '--properties-file', action = 'store', dest = 'propsfile', help = 'path to properties file')
    (options, args) = parser.parse_args()
    properties_filename = options.propsfile

    if not properties_filename:
        usage(parser)
    
    bot = TwitchBot(properties_filename)
    bot.start()

if __name__ == "__main__":
    main()
