#! /usr/bin/env pytho
import sys
import irc.bot
import requests
import os
import optparse
import MySQLdb
import csv
import random

# ---------------------------------------------------------------------------------------------
# globals
OUTPUT_FILE = sys.stdout
ERROR_FILE = sys.stderr

AUTOBOT_RESPONSES = {}
APPROVED_AUTO_SHOUTOUT_USERS = {}
CUSTOM_USER_SHOUTOUTS = {}
USERS_CHECKED = set()

# QUEUE
USER_QUEUE = {}
QUEUE_SCORE = {}

# ---------------------------------------------------------------------------------------------
# required properties
BOT_USERNAME = 'bot.username'
CHANNEL = 'channel.name'
CLIENT_ID = 'client_id'
CLIENT_SECRETS = 'client_secrets'
IRC_CHAT_SERVER_PORT = 'server.port'
IRC_CHAT_SERVER = 'server.url'
CHANNEL_TRUSTED_USERS_LIST = 'channel.trusted_users_list'
AUTO_SHOUTOUT_USERS_FILE = 'auto_shoutout_users_file'
CUSTOM_SHOUTOUTS_FILE = 'custom_shoutouts_file'
CUSTOM_USER_SHOUTOUT_MESSAGE_TEMPLATE = 'custom.user_shoutout_message'
IGNORED_USERS_LIST = 'ignored_users_list'
RESTRICTED_USERS_LIST = 'restricted_users_list'
RESTRICTED_USERS_COMMAND_COUNT = {}
QUEUE_NAMES_LIST = 'queue_names_list'
AUTOBOT_RESPONSES_FILE = 'auto_bot_responses_file'

# db properties
DB_HOST = 'db.host'
DB_NAME = 'db.db_name'
DB_USER = 'db.user'
DB_PW = 'db.password'
DB_PORT = 'db.port'

MSG_USERNAME_REPLACE_STRING = '${username}'
MSG_LAST_GAME_PLAYED_REPLACE_STRING = '${lastgameplayed}'
MSG_TWITCH_PAGE_URL_REPLACE_STRING = '${usertwitchpage}'

DEFAULT_USER_SHOUTOUT_MESSAGE_TEMPLATE = '@${username} is also a streamer! For some ${lastgameplayed} action, check them out some time at https://www.twitch.tv/${username}'

# valid commands
VALID_COMMANDS = ['game', 'title', 'so', 'death', 'print',
    'queueinit', 'score', 'streameraddnew', 'deathadd', 'deathreset',
    'deathinit', 'uptime', 'shoutout', 'songs', 'sr']

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

def parse_properties(properties_filename):
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
            value = property[1]
            if property[0] in [IGNORED_USERS_LIST, RESTRICTED_USERS_LIST, QUEUE_NAMES_LIST]:
                value = map(str.strip, value.split(','))
            properties[property[0]] = value

    # error check required properties
    if (CHANNEL not in properties or len(properties[CHANNEL]) == 0 or
        CLIENT_ID not in properties or len(properties[CLIENT_ID]) == 0 or
        CLIENT_SECRETS not in properties or len(properties[CLIENT_SECRETS]) == 0 or
        BOT_USERNAME not in properties or len(properties[BOT_USERNAME]) == 0 or
        IRC_CHAT_SERVER not in properties or len(properties[IRC_CHAT_SERVER]) == 0 or
        IRC_CHAT_SERVER_PORT not in properties or len(properties[IRC_CHAT_SERVER_PORT]) == 0):
        missing = [p for p in [CHANNEL, CLIENT_ID, CLIENT_SECRETS, BOT_USERNAME, IRC_CHAT_SERVER, IRC_CHAT_SERVER_PORT] if p not in properties.keys()]
        print >> ERROR_FILE, 'Missing one or more required properties, please check property file for the following: %s' % (', '.join(missing))
        sys.exit(2)

    # add broadcaster to list of users with mod permsissions
    trusted_users_list = set(map(str.strip, properties.get(CHANNEL_TRUSTED_USERS_LIST, '').split(',')))
    trusted_users_list.add(properties[CHANNEL])
    properties[CHANNEL_TRUSTED_USERS_LIST] = list(trusted_users_list)
    return properties

def encode_ascii_string(value):
    return value.encode('ascii', 'ignore')

class TwitchBot(irc.bot.SingleServerIRCBot):
    def __init__(self, properties):
        self.channel_display_name = properties[CHANNEL]
        self.channel = '#' + properties[CHANNEL]
        self.bot_username = properties[BOT_USERNAME]
        self.client_id = properties[CLIENT_ID]
        self.token = properties[CLIENT_SECRETS]
        self.auto_shoutout_users_file = properties.get(AUTO_SHOUTOUT_USERS_FILE, '')
        self.auto_bot_responses_file = properties.get(AUTOBOT_RESPONSES_FILE, '')
        self.custom_shoutouts_file = properties.get(CUSTOM_SHOUTOUTS_FILE, '')
        self.death_count = 0
        self.channel_id = self.get_channel_id(properties[CHANNEL])
        self.trusted_users_list = properties[CHANNEL_TRUSTED_USERS_LIST]
        self.ignored_users_list = properties.get(IGNORED_USERS_LIST, [])
        self.restricted_users_list = properties.get(RESTRICTED_USERS_LIST, [])
        self.queue_names_list = properties.get(QUEUE_NAMES_LIST, [])

        self.user_shoutout_message_template = DEFAULT_USER_SHOUTOUT_MESSAGE_TEMPLATE
        if CUSTOM_USER_SHOUTOUT_MESSAGE_TEMPLATE in properties and properties[CUSTOM_USER_SHOUTOUT_MESSAGE_TEMPLATE]:
            self.user_shoutout_message_template = properties[CUSTOM_USER_SHOUTOUT_MESSAGE_TEMPLATE]
        # self.db_connection = establish_db_connection(properties)

        # init auto shoutout list for auto-shoutouts (optional)
        if self.auto_shoutout_users_file != '' and os.path.exists(self.auto_shoutout_users_file):
            self.init_auto_shoutout_users(self.auto_shoutout_users_file)

        # init auto responses for bot (optional)
        if self.auto_bot_responses_file != '' and os.path.exists(self.auto_bot_responses_file):
            self.init_autobot_responses(self.auto_bot_responses_file)

        if self.custom_shoutouts_file != '' and os.path.exists(self.custom_shoutouts_file):
            self.init_custom_shoutout_users(self.custom_shoutouts_file)

        server = properties[IRC_CHAT_SERVER]
        port = int(properties[IRC_CHAT_SERVER_PORT])

        # Create IRC bot connection
        print >> OUTPUT_FILE, 'Connecting to %s on port %s...' % (server, port)
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, 'oauth:'+ self.token)], self.channel_display_name, self.bot_username)

    def init_auto_shoutout_users(self, auto_shoutout_users_filename):
        with open (auto_shoutout_users_filename, 'rU') as auto_shoutout_users_file:
            for username in auto_shoutout_users_file.readlines():
                APPROVED_AUTO_SHOUTOUT_USERS[username.strip()] = False

    def init_autobot_responses(self, auto_bot_responses_filename):
        with open(auto_bot_responses_filename, 'rU') as auto_bot_responses_file:
            for line in csv.DictReader(auto_bot_responses_file, dialect = 'excel-tab'):
                message = line['MESSAGE'].lower().strip()
                bot_responses = AUTOBOT_RESPONSES.get(message, [])
                bot_responses.append(line['RESPONSE'])
                AUTOBOT_RESPONSES[message] = list(set(bot_responses))

    def init_custom_shoutout_users(self, custom_shoutouts_filename):
        with open(custom_shoutouts_filename, 'rU') as custom_shoutouts_file:
            for record in csv.DictReader(custom_shoutouts_file, dialect='excel-tab'):
                if not 'TWITCH_USERNAME' in record.keys() or not 'SHOUTOUT_MESSAGE' in record.keys():
                    print >> ERROR_FILE, 'Custom shoutout file does not contain one or more of required headers:: "TWITCH_USERNAME", "SHOUTOUT_MESSAGE"'
                    sys.exit(2)
                CUSTOM_USER_SHOUTOUTS[record['TWITCH_USERNAME']] = record['SHOUTOUT_MESSAGE']

    def on_welcome(self, c, e):
        ''' Handle welcome. '''
        print >> OUTPUT_FILE, 'Joining channel: %s' % (self.channel)
        c.cap('REQ', ':twitch.tv/membership')
        c.cap('REQ', ':twitch.tv/tags')
        c.cap('REQ', ':twitch.tv/commands')
        c.join(self.channel)

    def on_pubmsg(self, c, e):
        ''' Handles message in chat. '''
        user_message = e.arguments[0].encode('ascii', 'ignore').strip().lower()
        if user_message ==  '!':
            return
        if user_message in AUTOBOT_RESPONSES.keys():
            self.send_auto_bot_response(user_message)
            return
        cmd_issuer = self.get_username(e)
        if cmd_issuer in self.restricted_users_list and user_message.startswith('!'):
            RESTRICTED_USERS_COMMAND_COUNT[cmd_issuer] = RESTRICTED_USERS_COMMAND_COUNT.get(cmd_issuer, 0) + 1
            if RESTRICTED_USERS_COMMAND_COUNT[cmd_issuer] > 5:
                c.privmsg(self.channel, '%s your use of commands has been suspended temporarily for overusage Kappa' % (cmd_issuer))
                return

        # give a streamer shoutout if viewer is in the approved streamers set
        # and streamer has not already gotten a shout out
        # (i.e., manual shoutout with !so <username> command)
        if not user_message.startswith('!'):
            self.auto_streamer_shoutout(e)
        else:
            # If a chat message starts with an exclamation point, try to run it as a command
            try:
                parsed_args = map(lambda x: str(x).lower(), encode_ascii_string(user_message).split(' '))
            except UnicodeEncodeError:
                print >> ERROR_FILE, "[UnicodeEncodeError], Error parsing command."
                return
            ##TODO: REPLACE WITH REGEX
            cmd = parsed_args[0].replace('!','')
            cmd_args = []
            if len(parsed_args) > 1:
                cmd_args = map(lambda x: x.replace('@',''), parsed_args[1:])
            print >> OUTPUT_FILE, 'Received command: %s with args: %s' % (cmd, ', '.join(cmd_args))
            self.do_command(e, cmd_issuer, cmd, cmd_args)
            return

    def send_auto_bot_response(self, message):
        ''' Sends custom response to matching messages in chat. '''
        c = self.connection
        response = ''
        if len(AUTOBOT_RESPONSES[message]) == 1:
            response = AUTOBOT_RESPONSES[message][0]
        else:
            response = random.choice(AUTOBOT_RESPONSES[message])
        if response:
            c.privmsg(self.channel, response)
            return

    # ---------------------------------------------------------------------------------------------
    # FETCH CHANNEL / USER DETAILS
    def get_username(self, e):
        ''' Returns username for given event. '''
        user = [d['value'] for d in e.tags if d['key'] == 'display-name'][0]
        return encode_ascii_string(user.lower())

    def user_is_mod(self, e):
        ''' Returns whether user has mod permissions. '''
        val = [d['value'] for d in e.tags if d['key'] == 'mod'][0]
        return (val == '1')

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
        try:
            game = encode_ascii_string(r['game'])
        except:
            game = 'None'
        return game

    def get_channel_title(self, e):
        ''' Returns channel title. '''
        url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
        headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
        r = requests.get(url, headers=headers).json()
        return encode_ascii_string(r['status'])

    def current_death_count(self, c):
        ''' Returns current death count. '''
        message = "@%s's current death count is %s ;___;" % (self.channel_display_name, self.death_count)
        c.privmsg(self.channel, message)

    # ---------------------------------------------------------------------------------------------
    # STREAMER SHOUTOUT FUNCTIONS
    def is_valid_user(self, user):
        ''' Determines whether user is valid for giving shout outs to or should be ignored. '''
        return (user not in self.ignored_users_list)

    def format_streamer_shoutout_message(self, user, game):
        message = CUSTOM_USER_SHOUTOUTS.get(user, self.user_shoutout_message_template)
        if MSG_USERNAME_REPLACE_STRING in message:
            message = message.replace(MSG_USERNAME_REPLACE_STRING, user)
        if MSG_LAST_GAME_PLAYED_REPLACE_STRING in message:
            message = message.replace(MSG_LAST_GAME_PLAYED_REPLACE_STRING, game)
        return encode_ascii_string(message)


    def streamer_shoutout_message(self, user):
        ''' Gives a streamer shoutout in twitch chat. '''
        if not self.is_valid_user(user):
            return

        c = self.connection
        if user == self.channel_display_name:
            c.privmsg(self.channel, 'Jebaited')
            return
        cid = self.get_channel_id(user)
        game = self.get_last_game_played(cid)
        if str(game) == 'None' and not user in CUSTOM_USER_SHOUTOUTS.keys():
            if user in APPROVED_AUTO_SHOUTOUT_USERS.keys():
                message = '%s streams but they are keeping their last game a played a secret Kappa' % (user)
            else:
                message = '%s is not a streamer BibleThump' % (user)
        else:
            message = self.format_streamer_shoutout_message(user, game)
            USERS_CHECKED.add(user)
        c.privmsg(self.channel, message)
        return

    def auto_streamer_shoutout(self, e):
        ''' Gives an automated streamer shoutout. '''
        c = self.connection
        user = self.get_username(e)
        if user in USERS_CHECKED:
            return
        if user in APPROVED_AUTO_SHOUTOUT_USERS and not APPROVED_AUTO_SHOUTOUT_USERS[user]:
            APPROVED_AUTO_SHOUTOUT_USERS[user] = True
            self.streamer_shoutout_message(user)
        USERS_CHECKED.add(user)
        return

    def update_approved_auto_shoutout_users_list(self, streamer):
        ''' Updates auto shoutout users file. This is only permitted for channel broadcaster. '''
        if not streamer in APPROVED_AUTO_SHOUTOUT_USERS.keys():
            APPROVED_AUTO_SHOUTOUT_USERS[streamer] = True
            if len(APPROVED_AUTO_SHOUTOUT_USERS.keys()) > 0:
                with open(self.auto_shoutout_users_file, 'w') as streamer_file:
                    streamer_file.write('\n'.join(APPROVED_AUTO_SHOUTOUT_USERS.keys()))

    # ---------------------------------------------------------------------------------------------
    # CUSTOM USER QUEUE FUNCTIONS
    def add_user_to_queue(self, user, input_queue_name):
        ''' Adds user to specified queue. '''
        c = self.connection
        other_queue_names = [queue for queue in self.queue_names_list if queue != input_queue_name]
        for q in other_queue_names:
            if user in USER_QUEUE.get(q, []):
                message = 'Hey %s, you are already in the queue for %s! You cannot join a different queue without leaving the one you are already in first. Leave the queue by entering !%s leave' % (user, q, q)
                c.privmsg(self.channel, message)
                return

        queue_list = USER_QUEUE.get(input_queue_name, [])
        if user in queue_list:
            message = 'Hey %s, you are already in the %s queue! Your position is #%s' % (user, input_queue_name, (queue_list.index(user) + 1))
        else:
            queue_list.append(user)
            USER_QUEUE[input_queue_name] = queue_list
            message = 'Hey %s, you have entered the queue for %s! Your position is #%s' % (user, input_queue_name, (queue_list.index(user) + 1))
        c.privmsg(self.channel, message)
        return

    def kick_user_from_queue(self, user, input_queue_name):
        ''' Kicks user from specified queue. '''
        c = self.connection
        queue_list = USER_QUEUE.get(input_queue_name, [])
        if user in queue_list:
            queue_list.remove(user)
            USER_QUEUE[input_queue_name] = queue_list
            message = '%s has left the queue for %s' % (user, input_queue_name)
        else:
            message = '%s - you cannot leave a queue you are not in Jebaited' % (user)
        c.privmsg(self.channel, message)
        return

    def get_next_user_in_queue(self, input_queue_name):
        ''' Returns next user in specified queue. '''
        if len(self.queue_names_list) == 0:
            return
        c = self.connection
        queue_list = USER_QUEUE.get(input_queue_name, [])
        if queue_list:
            next_user = queue_list.pop(0)
            message = 'Hey %s, you are up next for queue %s' % (next_user, input_queue_name)
            if len(queue_list) > 0:
                message += ';  %s is next in queue!' % (queue_list[0])
            USER_QUEUE[input_queue_name] = queue_list
        else:
            message = 'The queue for %s is empty ResidentSleeper' % (input_queue_name)
        c.privmsg(self.channel, message)
        return

    def print_current_score(self):
        ''' Prints current score. '''
        if len(self.queue_names_list) == 0:
            return
        c = self.connection
        score_board = []
        for q in self.queue_names_list:
            score_board.append('%s = %s win(s)' % (q, QUEUE_SCORE.get(q, 0)))
        message = 'Current scores: ' + ',  '.join(score_board)
        c.privmsg(self.channel, message)
        return

    def print_all_queues(self):
        '''  Prints all the queues. '''
        if len(self.queue_names_list) == 0:
            return
        c = self.connection
        current_queues = []
        for q in self.queue_names_list:
            if len(USER_QUEUE.get(q, [])) > 0:
                m = 'Current queue for %s: %s' % (q, ', '.join(USER_QUEUE[q]))
            else:
                m = 'Current queue for %s is empty BibleThump' % (q)
            current_queues.append(m)
        c.privmsg(self.channel, ';   '.join(current_queues))
        return

    def init_new_queue_list(self, queue_names_list):
        ''' Sets the available queues to join to the specified list. '''
        c = self.connection
        # confirm that the queue names are not already in the valid commands set so as to not confuse any bots
        invalid_queue_names = [q for q in queue_names_list if q in VALID_COMMANDS]
        if len(invalid_queue_names) > 0:
            message = 'Cannot set queue names to names of commands which already exist! Invalid queue names: %s' % (', '.join(invalid_queue_names))
        else:
            self.queue_names_list = queue_names_list[:]
            USER_QUEUE.clear()
            QUEUE_SCORE.clear()
            message = 'Available queue(s) to join: %s' % (', '.join(queue_names_list))
        c.privmsg(self.channel, message)
        return

    # ---------------------------------------------------------------------------------------------
    # BOT MAIN
    def do_command(self, e, cmd_issuer, cmd, cmd_args):
        c = self.connection
        user_has_mod_privileges = False
        if self.user_is_mod(e) or cmd_issuer in self.trusted_users_list:
            user_has_mod_privileges = True

        if cmd == "game":
            game = self.get_last_game_played(self.channel_id)
            c.privmsg(self.channel, self.channel_display_name + ' is currently playing ' + game)
        # Poll the API the get the current status of the stream
        elif cmd == "title":
            title = self.get_channel_title(self.channel_id)
            c.privmsg(self.channel, self.channel_display_name + ' channel title is currently ' + title)
        elif cmd == 'death':
            self.current_death_count(c)
        elif cmd == 'print' and len(self.queue_names_list) > 0:
            self.print_all_queues()
        elif cmd == 'score' and len(self.queue_names_list) > 0:
            self.print_current_score()
        elif cmd in self.queue_names_list:
            if not cmd_args:
                self.add_user_to_queue(cmd_issuer, cmd)
            elif 'leave' in cmd_args:
                self.kick_user_from_queue(cmd_issuer, cmd)
            elif 'next' in cmd_args and cmd_issuer == self.channel_display_name:
                self.get_next_user_in_queue(cmd)
            elif 'win' in cmd_args and cmd_issuer == self.channel_display_name:
                QUEUE_SCORE[cmd] = QUEUE_SCORE.get(cmd, 0) + 1
                self.print_current_score()
        elif cmd == 'queueinit' and cmd_issuer == self.channel_display_name and len(cmd_args) > 0:
            self.init_new_queue_list(cmd_args)
        elif user_has_mod_privileges:
            if cmd == 'deathadd':
                self.death_count += 1
                c.privmsg(self.channel, "%s's current death count is now %s ;___;" % (self.channel_display_name, self.death_count))
            elif cmd == 'deathreset':
                self.death_count = 0
                c.privmsg(self.channel, "%s reset their current death count :P" % (self.channel_display_name))
            elif cmd == 'deathinit':
                self.death_count = int(cmd_args[0])
                c.privmsg(self.channel, "%s initialized their current death count to %s" % (self.channel_display_name, self.death_count))
            elif cmd == "so" and len(cmd_args) > 0:
                self.streamer_shoutout_message(cmd_args[0])
        elif cmd_issuer == self.channel_display_name:
            if cmd == "streameraddnew":
                self.update_approved_auto_shoutout_users_list(cmd_args[0])

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
    properties = parse_properties(properties_filename)

    bot = TwitchBot(properties)
    bot.start()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print >> OUTPUT_FILE, '\nBye!'
