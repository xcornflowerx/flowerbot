#! /usr/bin/env pytho
import sys
import irc.bot
import requests
import os
import optparse
import MySQLdb
import csv
import random
import operator

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

# flowermons properties
FLOWERMONS_ENABLED = 'flowermons.enabled'
FLOWERMONS_FILENAME = 'flowermons.filename'
FLOWERMONS_USER_DATA_FILENAME = 'flowermons.user_data_filename'
FLOWERMONS_SUBS_ONLY_MODE = 'flowermons.subs_only_mode'
FLOWERMONS_DEFAULT_POKEBALL_LIMIT = 'flowermons.default_pokeball_limit'
FLOWERMONS_SUBSCRIBERS_POKEBALL_LIMIT = 'flowermons.subs_pokeball_limit'


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

# FLOWERMONS
FLOWERMONS_POKEDEX = set()
FLOWERMONS_USER_POKEDEX = {}
FLOWERMONS_USER_POKEBALLS = {}

# valid commands
VALID_COMMANDS = ['game', 'title', 'so', 'death', 'print',
    'queueinit', 'score', 'streameraddnew', 'deathadd', 'deathreset',
    'deathinit', 'uptime', 'shoutout', 'songs', 'sr',
    'flowerdex', 'catch']

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
        self.flowermons_enabled = (properties.get(FLOWERMONS_ENABLED, 'false') == 'true')
        self.flowermons_filename = properties.get(FLOWERMONS_FILENAME, '')
        self.flowermons_user_data_filename = properties.get(FLOWERMONS_USER_DATA_FILENAME, '')
        self.flowermons_subs_only_mode = (properties.get(FLOWERMONS_SUBS_ONLY_MODE, 'false') == 'true')
        self.flowermons_default_pokeball_limit = int(properties.get(FLOWERMONS_DEFAULT_POKEBALL_LIMIT, 3))
        self.flowermons_subscribers_pokeball_limit = int(properties.get(FLOWERMONS_SUBSCRIBERS_POKEBALL_LIMIT, 10))

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

        if self.flowermons_enabled:
            if self.flowermons_filename != '' and os.path.exists(self.flowermons_filename):
                self.init_flowermons_pokedex(self.flowermons_filename)
            if self.flowermons_user_data_filename != '':
                self.load_flowermons_user_data(self.flowermons_user_data_filename)


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

    def init_flowermons_pokedex(self, flowermons_filename):
        with open(flowermons_filename, 'rU') as flowermons_file:
            for line in flowermons_file.readlines():
                FLOWERMONS_POKEDEX.add(line.strip().lower())

    def load_flowermons_user_data(self, flowermons_user_data_filename):
        if os.path.exists(flowermons_user_data_filename):
            with open(flowermons_user_data_filename, 'rU') as flowermons_user_data_file:
                for line in flowermons_user_data_file.readlines():
                    data = map(lambda x: x.strip().lower(), line.split('\t'))
                    username = data[0]
                    user_pokemon_set = FLOWERMONS_USER_POKEDEX.get(username, set())
                    user_pokemon_set.add(data[1])
                    FLOWERMONS_USER_POKEDEX[username] = user_pokemon_set

    def on_welcome(self, c, e):
        ''' Handle welcome. '''
        print >> OUTPUT_FILE, 'Joining channel: %s' % (self.channel)
        c.cap('REQ', ':twitch.tv/membership')
        c.cap('REQ', ':twitch.tv/tags')
        c.cap('REQ', ':twitch.tv/commands')
        c.join(self.channel)

    def on_all_raw_messages(self, c, e):
        print >> OUTPUT_FILE, e

    def on_pubmsg(self, c, e):
        ''' Handles message in chat. '''

        # give a streamer shoutout if viewer is in the approved streamers set
        # and streamer has not already gotten a shout out
        # (i.e., manual shoutout with !so <username> command)
        self.auto_streamer_shoutout(e)

        user_message = e.arguments[0].encode('ascii', 'ignore').strip().lower()
        if user_message in AUTOBOT_RESPONSES.keys():
            self.send_auto_bot_response(user_message)
            return
        cmd_issuer = self.get_username(e)
        if cmd_issuer in self.restricted_users_list and user_message.startswith('!'):
            RESTRICTED_USERS_COMMAND_COUNT[cmd_issuer] = RESTRICTED_USERS_COMMAND_COUNT.get(cmd_issuer, 0) + 1
            if RESTRICTED_USERS_COMMAND_COUNT[cmd_issuer] > 5:
                c.privmsg(self.channel, '%s your use of commands has been suspended temporarily for overusage Kappa' % (cmd_issuer))
                return

        # If a chat message starts with an exclamation point, try to run it as a command
        try:
            parsed_args = map(lambda x: str(x).lower(), encode_ascii_string(user_message).split(' '))
        except UnicodeEncodeError:
            print >> ERROR_FILE, "[UnicodeEncodeError], Error parsing command."
            return
        ##TODO: REPLACE WITH REGEX
        if not parsed_args[0].startswith('!'):
            return
        cmd = parsed_args[0].replace('!','')
        cmd_args = []
        if len(parsed_args) > 1:
            cmd_args = map(lambda x: x.replace('@',''), parsed_args[1:])
        print >> OUTPUT_FILE, 'Received command: %s with args: %s' % (cmd, ', '.join(cmd_args))
        try:
            self.do_command(e, cmd_issuer, cmd, cmd_args)
        except Exception as e:
            print >> OUTPUT_FILE, e
        return

    def send_auto_bot_response(self, message):
        '''
            Sends custom response to matching messages in chat.
            Always send response if message startswith '!', otherwise
            randomly decide whether to send response.
        '''
        c = self.connection
        response = response = random.choice(AUTOBOT_RESPONSES[message])
        send_message = True
        if not message.startswith('!'):
            send_message = random.choice([True, False, False])
        if response and send_message:
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

    def user_is_sub(self, e):
        ''' Returns whether user is a subscriber. '''
        sub_founder_status = False
        for d in e.tags:
            if d['key'] in ['subscriber', 'founder']:
                if d['value'][0] == '1':
                    sub_founder_status = True
                    break
        return sub_founder_status

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
        message = "@%s's current death count is %s" % (self.channel_display_name, self.death_count)
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
                message = "%s streams but they are keeping their last game a played a secret Kappa" % (user)
            else:
                message = "%s is not a streamer BibleThump" % (user)
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
        # check if user already exists in one of the available queues
        (user_queue, user_position) = self.get_user_queue_and_position(user)

        # if user in another queue then user must leave it to enter a different queue
        if user_queue:
            if user_queue != input_queue_name:
                message = "Hey %s, you are already in the queue for %s! You cannot join a different queue without leaving the one you are already in first. Leave the queue by entering '!leave'" % (user, user_queue)
            else:
                message = "Hey %s, you are already in the %s queue! Your position is #%s" % (user, user_queue, user_position)
        else:
            queue_list = USER_QUEUE.get(input_queue_name, [])
            queue_list.append(user)
            USER_QUEUE[input_queue_name] = queue_list
            message = 'Hey %s, you have entered the queue for %s! Your position is #%s' % (user, input_queue_name, (queue_list.index(user) + 1))
        c.privmsg(self.channel, message)
        return

    def get_user_queue_and_position(self, user):
        ''' Returns which queue the user is in and their position in the queue. '''
        user_queue = ''
        user_position = -1
        for queue in self.queue_names_list:
            queue_list = USER_QUEUE.get(queue, [])
            if user in queue_list:
                user_queue = queue
                user_position = queue_list.index(user) + 1
                break
        return (user_queue, user_position)

    def kick_user_from_queue(self, user):
        ''' Kicks user from specified queue. '''
        c = self.connection
        (user_queue_name, user_position) = self.get_user_queue_and_position(user)
        if user_queue_name:
            queue_list = USER_QUEUE.get(user_queue_name, [])
            queue_list.remove(user)
            USER_QUEUE[user_queue_name] = queue_list
            message = '%s has left the queue for %s' % (user, user_queue_name)
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
                m = "Current queue for %s: %s" % (q, ', '.join(USER_QUEUE[q]))
            else:
                m = "Current queue for %s is empty BibleThump" % (q)
            current_queues.append(m)
        c.privmsg(self.channel, ';   '.join(current_queues))
        return

    def format_available_queues_message(self):
        ''' Prints the available queues to join. '''
        available_queues_message = "There aren't any queues available to join at this time."
        if len(self.queue_names_list) > 0:
            available_queues_message = "Available queue(s) to join: %s - use ![queue name] to join" % (', '.join(self.queue_names_list))
        return available_queues_message

    def print_available_queues(self):
        ''' Shares which queues are available to join. '''
        c = self.connection
        c.privmsg(self.channel, self.format_available_queues_message())
        return

    def print_user_position_in_queue(self, user):
        ''' Prints user's current position in queue. '''
        c = self.connection
        (user_queue, user_position) = self.get_user_queue_and_position(user)
        if user_queue:
            message = "Hey %s, you are in queue %s and your position is #%s" % (user, user_queue, user_position)
        else:
            message = "Hey %s, you are not in any queues yet. Use '!queues' to see which queues are available to join." % (user)
        c.privmsg(self.channel, message)
        return

    def init_new_queue_list(self, queue_names_list):
        ''' Sets the available queues to join to the specified list. '''
        c = self.connection
        # confirm that the queue names are not already in the valid commands set so as to not confuse any bots
        invalid_queue_names = [q for q in queue_names_list if q in VALID_COMMANDS]
        if len(invalid_queue_names) > 0:
            message = "Cannot set queue names to names of commands which already exist! Invalid queue names: %s" % (', '.join(invalid_queue_names))
        else:
            self.queue_names_list = queue_names_list[:]
            USER_QUEUE.clear()
            QUEUE_SCORE.clear()
            message = self.format_available_queues_message()
        c.privmsg(self.channel, message)
        return

    # ---------------------------------------------------------------------------------------------
    # FLOWERMONS

    def format_flowerdex_check_message(self, cmd_issuer, user_is_sub):
        caught_mons = FLOWERMONS_USER_POKEDEX.get(cmd_issuer, set())
        if len(caught_mons) > 0:
            message = '@%s your FlowerDex is %s%% complete and you have %s Flowerballs left!' % (cmd_issuer, self.calculate_flowerdex_completion(cmd_issuer), self.get_users_pokeball_count(cmd_issuer, user_is_sub))
        else:
            message = '@%s you have not caught any pokemon yet :(' % (cmd_issuer)
        return message

    def check_flowerdex(self, cmd_issuer, user_is_sub):
        c = self.connection
        c.privmsg(self.channel, self.format_flowerdex_check_message(cmd_issuer, user_is_sub))
        return

    def calculate_flowerdex_completion(self, cmd_issuer):
        caught_mons = FLOWERMONS_USER_POKEDEX.get(cmd_issuer, set())
        return (100 * len(caught_mons) / len(FLOWERMONS_POKEDEX))

    def catch_flowermon(self, cmd_issuer, user_is_sub):
        ''' Catches random pokemon for user and stores mon in flowerdex. '''
        c = self.connection
        pokeballs = self.get_users_pokeball_count(cmd_issuer, user_is_sub)
        if pokeballs == 0:
            c.privmsg(self.channel, '@%s, you do not have any flowerballs left! BibleThump' % (cmd_issuer))
            return
        pokemon = random.choice(list(FLOWERMONS_POKEDEX))
        self.store_caught_pokemon(cmd_issuer, pokemon)

        FLOWERMONS_USER_POKEBALLS[cmd_issuer] = pokeballs - 1

        message = '@%s caught %s! %s' % (cmd_issuer, pokemon.title(), self.format_flowerdex_check_message(cmd_issuer, user_is_sub))
        if pokemon == 'jigglypuff' and cmd_issuer != 'vudoo781':
            message += '... speaking of jigglypuff ... @vudoo781 would like a word with you Kappa'
        try:
            c.privmsg(self.channel, message)
        except Exception as e:
            print >> OUTPUT_FILE, e
            print >> OUTPUT_FILE, message
            c.privmsg(self.channel, 'whoops BibleThump @%s broke me snowpoNK' % (cmd_issuer))
        return

    def store_caught_pokemon(self, cmd_issuer, pokemon):
        ''' Stores pokemon in data file for user. '''
        user_pokemon_set = FLOWERMONS_USER_POKEDEX.get(cmd_issuer, set())
        user_pokemon_set.add(pokemon)
        FLOWERMONS_USER_POKEDEX[cmd_issuer] = user_pokemon_set
        self.update_flowermons_user_pokedex_data_file()

    def update_flowermons_user_pokedex_data_file(self):
        ''' Updates Flowermons user data file. '''
        with open(self.flowermons_user_data_filename, 'w') as flowermons_user_data_file:
            for user, user_pokemon_set in FLOWERMONS_USER_POKEDEX.items():
                for pokemon in user_pokemon_set:
                    flowermons_user_data_file.write('%s\t%s\n' % (user, pokemon))

    def get_users_pokeball_count(self, cmd_issuer, user_is_sub):
        ''' Returns number of pokeballs user has left. '''
        if not cmd_issuer in FLOWERMONS_USER_POKEBALLS.keys():
            if user_is_sub:
                FLOWERMONS_USER_POKEBALLS[cmd_issuer] = self.flowermons_subscribers_pokeball_limit
            else:
                FLOWERMONS_USER_POKEBALLS[cmd_issuer] = self.flowermons_default_pokeball_limit
        return FLOWERMONS_USER_POKEBALLS[cmd_issuer]

    def print_flowerdex_leaders_message(self):
        ''' Prings current FlowerDex leaders. '''
        c = self.connection
        if len(FLOWERMONS_USER_POKEDEX) == 0:
            return
        flowerdex_leaders = self.get_flowerdex_leaders_set()
        message = "Current top 5 FlowerDex leaders are:  %s (%s%%)" % (', '.join(flowerdex_leaders[0][1]), flowerdex_leaders[0][0])
        if len(flowerdex_leaders) > 1:
            for flowerdex_completion_value,tied_users_by_flowerdex_completion_value in flowerdex_leaders[1:]:
                message += "  //  %s (%s%%)" % (', '.join(tied_users_by_flowerdex_completion_value), flowerdex_completion_value)
        c.privmsg(self.channel, message)
        return

    def get_flowerdex_leaders_set(self):
        '''
            Returns the 5 users with the most (unique) flowermons.
            If multiple users are tied for 5th then they are also included in the set of users returned.
        '''
        flowerdex_completion_by_values = {}
        for user in FLOWERMONS_USER_POKEDEX.keys():
            flowerdex_completion_value = self.calculate_flowerdex_completion(user)
            tied_users_by_flowerdex_completion_value = flowerdex_completion_by_values.get(flowerdex_completion_value, [])
            tied_users_by_flowerdex_completion_value.append(user)
            flowerdex_completion_by_values[flowerdex_completion_value] = tied_users_by_flowerdex_completion_value
        leaders = []
        for flowerdex_completion_value,tied_users_by_flowerdex_completion_value in sorted(flowerdex_completion_by_values.items(), key = operator.itemgetter(0), reverse = True):
            leaders.append((flowerdex_completion_value, tied_users_by_flowerdex_completion_value))
            if len(leaders) >= 5:
                break
        return leaders

    def add_balls_purchased_with_bits(self, username, num_bits_used, user_is_sub):
        ''' Add balls for users who purchase pokeballs for bits. A bonus ball is given for every 200 bits donated. '''
        balls_purchased = num_bits_used / 50
        bonus_balls = num_bits_used / 200;
        current_num_balls = self.get_users_pokeball_count(username, user_is_sub)
        FLOWERMONS_USER_POKEBALLS[username] = current_num_balls + balls_purchased + bonus_balls
        c = self.connection
        c.privmsg(self.channel, '%s now has %s flowerballs!' % (username, FLOWERMONS_USER_POKEBALLS[username]))
        return

    def add_balls_by_amount(self, username, num_balls, user_is_sub):
        ''' Add balls for users who purchase pokeballs for bits. A bonus ball is given for every 200 bits donated. '''
        current_num_balls = self.get_users_pokeball_count(username, user_is_sub)
        FLOWERMONS_USER_POKEBALLS[username] = current_num_balls + num_balls
        c = self.connection
        c.privmsg(self.channel, '%s now has %s flowerballs!' % (username, FLOWERMONS_USER_POKEBALLS[username]))
        return

    def purchase_flowerballs(self, username, purchase_type, ball_or_bits_amount, user_is_sub):
        ''' Add balls for user by bits purchased or actual number of balls to add. '''
        if purchase_type in ['bits', 'dollars']:
            if purchase_type == 'dollars':
                ball_or_bits_amount = ball_or_bits_amount * 100
            self.add_balls_purchased_with_bits(username, ball_or_bits_amount, user_is_sub)
        elif purchase_type == 'balls':
            self.add_balls_by_amount(username, ball_or_bits_amount, user_is_sub)
        else:
            c = self.connection
            c.privmsg(self.channel, '"%s" is an invalid way to add balls for a user' % (purchase_type))
        return

    # ---------------------------------------------------------------------------------------------
    # BOT MAIN
    def do_command(self, e, cmd_issuer, cmd, cmd_args):
        c = self.connection
        user_has_mod_privileges = False
        if self.user_is_mod(e) or cmd_issuer in self.trusted_users_list:
            user_has_mod_privileges = True
        user_is_sub = self.user_is_sub(e)

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
        elif len(self.queue_names_list) > 0 and (cmd in self.queue_names_list):
            if not cmd_args:
                self.add_user_to_queue(cmd_issuer, cmd)
            elif 'leave' in cmd_args or cmd == 'leave':
                self.kick_user_from_queue(cmd_issuer)
            elif 'next' in cmd_args and cmd_issuer == self.channel_display_name:
                self.get_next_user_in_queue(cmd)
            elif 'win' in cmd_args and cmd_issuer == self.channel_display_name:
                QUEUE_SCORE[cmd] = QUEUE_SCORE.get(cmd, 0) + 1
                self.print_current_score()
            elif cmd in ['join', 'list', 'queues']:
                self.print_available_queues()
            elif cmd == 'position':
                self.print_user_position_in_queue(cmd_issuer)
        elif self.flowermons_enabled and cmd in ['flowerdex', 'catch', 'addballs', 'leaders']:
            if cmd == 'addballs' and cmd_issuer == self.channel_display_name:
                username = cmd_args[0]
                purchase_type = cmd_args[1]
                ball_or_bits_amount = int(float(cmd_args[2]))
                self.purchase_flowerballs(username, purchase_type, ball_or_bits_amount, user_is_sub)
                return
            if self.flowermons_subs_only_mode and not user_is_sub:
                c.privmsg(self.channel, 'Flowermons is running in subs-only mode.')
            else:
                if cmd == 'flowerdex':
                    self.check_flowerdex(cmd_issuer, user_is_sub)
                elif cmd == 'leaders':
                    self.print_flowerdex_leaders_message()
                elif cmd == 'catch':
                    self.catch_flowermon(cmd_issuer, user_is_sub)
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
