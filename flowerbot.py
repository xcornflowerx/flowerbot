#! /usr/bin/env pytho
import sys
import irc.bot
import requests
import os
import optparse
import csv
import random
import operator
import math
from playsound import playsound
from datetime import datetime, date

# ---------------------------------------------------------------------------------------------
# globals
OUTPUT_FILE = sys.stdout
ERROR_FILE = sys.stderr

AUTOBOT_RESPONSES = {}
APPROVED_AUTO_SHOUTOUT_USERS = {}
CUSTOM_USER_SHOUTOUTS = {}
USERS_CHECKED = set()

# SYSTEM GLOBALS
CURRENT_DIR = os.getcwd()
RESOURCES_DIR = os.path.join(CURRENT_DIR, 'resources')
DATA_DIRECTORY = os.path.join(RESOURCES_DIR, 'data')
FLOWERMONS_DIRECTORY = os.path.join(DATA_DIRECTORY, 'mons')
# ---------------------------------------------------------------------------------------------
# required properties
BOT_USERNAME = 'bot.username'
CHANNEL = 'channel.name'
CHANNEL_ID = 'channel.id'
CLIENT_ID = 'client_id'
CLIENT_SECRETS = 'client_secrets'
IRC_CHAT_SERVER_PORT = 'server.port'
IRC_CHAT_SERVER = 'server.url'
CHANNEL_TRUSTED_USERS_LIST = 'channel.trusted_users_list'
AUTO_SHOUTOUT_USERS_FILE = 'auto_shoutout_users_file'
CUSTOM_SHOUTOUTS_FILE = 'custom_shoutouts_file'
CUSTOM_USER_SHOUTOUT_MESSAGE_TEMPLATE = 'custom.user_shoutout_message'
IGNORED_USERS_LIST = 'ignored_users_list'
AUTOBOT_RESPONSES_FILE = 'auto_bot_responses_file'
SFX_DIRECTORY = 'sfx.directory'

# flowermons properties
FLOWERMONS_ENABLED = 'flowermons.enabled'
FLOWERMONS_FILENAME = 'flowermons.filename'
FLOWERMONS_USER_DATA_FILENAME = 'flowermons.user_data_filename'
FLOWERMONS_SUBS_ONLY_MODE = 'flowermons.subs_only_mode'
FLOWERMONS_DEFAULT_POKEBALL_LIMIT = 'flowermons.default_pokeball_limit'
FLOWERMONS_SUBSCRIBERS_POKEBALL_LIMIT = 'flowermons.subs_pokeball_limit'

MSG_USERNAME_REPLACE_STRING = '${username}'
MSG_LAST_GAME_PLAYED_REPLACE_STRING = '${lastgameplayed}'
MSG_TWITCH_PAGE_URL_REPLACE_STRING = '${usertwitchpage}'
DEFAULT_USER_SHOUTOUT_MESSAGE_TEMPLATE = '@${username} is also a streamer! Check them out some time at https://www.twitch.tv/${username}'

# FLOWERMONS
FLOWERMONS_POKEDEX = set()
FLOWERMONS_USER_POKEDEX = {}
FLOWERMONS_USER_POKEBALLS = {}
FLOWERMONS_SUB_SHINY_DENOM = 256

# valid commands
VALID_COMMANDS = ['game', 'title', 'so', 'death', 'print',
    'score', 'streameraddnew', 'deathadd', 'deathreset',
    'deathinit', 'shoutout', 'flowerdex', 'catch', 'flowermons', 'addballs']

## TODO: move mappings to data file :)
SFX_MAPPINGS = {
    'shiny' : 'shiny_sfx.mp3',
    'rafakp' : 'emf_sample_audio_trimmed.mp3',
    'sin_elite': 'twilightzone_cut.mp3'
}

# ---------------------------------------------------------------------------------------------
# db functions

def parse_properties(properties_filename):
    ''' Parses the properties file. '''
    properties = {}
    with open(properties_filename, 'r', encoding = "utf8") as properties_file:
        for line in properties_file:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            property = list(map(str.strip, line.split('=')))
            if len(property) != 2:
                continue
            value = property[1]
            properties[property[0]] = value

    # error check required properties
    if (CHANNEL not in properties or len(properties[CHANNEL]) == 0 or
        CLIENT_ID not in properties or len(properties[CLIENT_ID]) == 0 or
        CLIENT_SECRETS not in properties or len(properties[CLIENT_SECRETS]) == 0 or
        BOT_USERNAME not in properties or len(properties[BOT_USERNAME]) == 0 or
        IRC_CHAT_SERVER not in properties or len(properties[IRC_CHAT_SERVER]) == 0 or
        IRC_CHAT_SERVER_PORT not in properties or len(properties[IRC_CHAT_SERVER_PORT]) == 0):
        missing = [p for p in [CHANNEL, CLIENT_ID, CLIENT_SECRETS, BOT_USERNAME, IRC_CHAT_SERVER, IRC_CHAT_SERVER_PORT] if p not in properties.keys()]
        print('Missing one or more required properties, please check property file for the following: %s' % (', '.join(missing)), file = ERROR_FILE)
        sys.exit(2)

    # add broadcaster to list of users with mod permsissions
    trusted_users_list = set(map(str.strip, properties.get(CHANNEL_TRUSTED_USERS_LIST, '').split(',')))
    trusted_users_list.add(properties[CHANNEL])
    properties[CHANNEL_TRUSTED_USERS_LIST] = list(trusted_users_list)
    return properties

def encode_ascii_string(value):
    return value.encode('ascii', 'ignore').decode('utf-8')

class TwitchBot(irc.bot.SingleServerIRCBot):
    def __init__(self, properties):
        self.channel_display_name = properties[CHANNEL]
        self.channel = '#' + properties[CHANNEL]
        self.bot_username = properties[BOT_USERNAME]
        self.client_id = properties[CLIENT_ID]
        self.token = properties[CLIENT_SECRETS]
        self.auto_shoutout_users_file = os.path.join(DATA_DIRECTORY, properties.get(AUTO_SHOUTOUT_USERS_FILE, ''))
        self.auto_bot_responses_file = os.path.join(DATA_DIRECTORY, properties.get(AUTOBOT_RESPONSES_FILE, ''))
        self.custom_shoutouts_file = os.path.join(DATA_DIRECTORY, properties.get(CUSTOM_SHOUTOUTS_FILE, ''))
        self.sfx_directory = os.path.join(RESOURCES_DIR, 'sfx')

        self.death_count = 0
        self.channel_id = properties[CHANNEL_ID]
        self.trusted_users_list = properties[CHANNEL_TRUSTED_USERS_LIST]
        self.ignored_users_list = properties.get(IGNORED_USERS_LIST, [])
        self.flowermons_enabled = (properties.get(FLOWERMONS_ENABLED, 'false') == 'true')
        self.flowermons_filename = os.path.join(FLOWERMONS_DIRECTORY, properties.get(FLOWERMONS_FILENAME, ''))
        self.flowermons_user_data_filename = os.path.join(FLOWERMONS_DIRECTORY, properties.get(FLOWERMONS_USER_DATA_FILENAME, '')) 
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
        print('Connecting to %s on port %s...' % (server, port), file = OUTPUT_FILE)
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, 'oauth:'+ self.token)], self.channel_display_name, self.bot_username)

    def print_message_to_chat(self, message):
        c = self.connection
        c.privmsg(self.channel, message)
        return

    def init_auto_shoutout_users(self, auto_shoutout_users_filename):
        with open (auto_shoutout_users_filename, 'r', encoding = "utf8") as auto_shoutout_users_file:
            for username in auto_shoutout_users_file.readlines():
                APPROVED_AUTO_SHOUTOUT_USERS[username.strip()] = False

    def init_autobot_responses(self, auto_bot_responses_filename):
        with open(auto_bot_responses_filename, 'r', encoding = "utf8") as auto_bot_responses_file:
            for line in csv.DictReader(auto_bot_responses_file, dialect = 'excel-tab'):
                message = line['MESSAGE'].lower().strip()
                bot_responses = AUTOBOT_RESPONSES.get(message, [])
                bot_responses.append(line['RESPONSE'])
                AUTOBOT_RESPONSES[message] = list(set(bot_responses))

#### TODO: Fix how commands are updated 
    # def update_autobot_responses_file(self):
    #     with open(self.auto_bot_responses_filename, 'w', encoding = 'utf8') as auto_bot_responses_file:
    #         file_header = ['MESSAGE', 'RESPONSE']
    #         auto_bot_responses_file.write('\t'.join(file_header))
    #         auto_bot_responses_file.write('\n')
    #         for cmd,message_list in AUTOBOT_RESPONSES.items():
    #             for message in message_list:
    #                 auto_bot_responses_file.write(cmd)
    #                 auto_bot_responses_file.write('\t')
    #                 auto_bot_responses_file.write(message)
    #                 auto_bot_responses_file.write('\n')

    # def edit_existing_command(self, cmd, response):
    #     AUTOBOT_RESPONSES[cmd.lower()] = response
    #     self.update_autobot_responses_file()

    # def add_new_command(self, cmd, response):
    #     cmd = cmd.lower()
    #     if cmd in AUTOBOT_RESPONSES.keys():
    #         message = 'Command %s already exists - use !editcmd to edit an existing command' % cmd
    #         self.print_message_to_chat(message)
    #     else:
    #         AUTOBOT_RESPONSES[cmd] = response
    #         self.update_autobot_responses_file()

    # def add_new_alias_keyword(self, cmd, response):
    #     cmd = cmd.lower()
    #     existing_responses = AUTOBOT_RESPONSES.get(cmd, [])
    #     existing_responses.append(response)
    #     AUTOBOT_RESPONSES[cmd] = existing_responses
    #     self.update_autobot_responses_file()

    def init_custom_shoutout_users(self, custom_shoutouts_filename):
        with open(custom_shoutouts_filename, 'r', encoding = "utf8") as custom_shoutouts_file:
            for record in csv.DictReader(custom_shoutouts_file, dialect='excel-tab'):
                if not 'TWITCH_USERNAME' in record.keys() or not 'SHOUTOUT_MESSAGE' in record.keys():
                    print('Custom shoutout file does not contain one or more of required headers:: "TWITCH_USERNAME", "SHOUTOUT_MESSAGE"', file = ERROR_FILE)
                    sys.exit(2)
                CUSTOM_USER_SHOUTOUTS[record['TWITCH_USERNAME']] = record['SHOUTOUT_MESSAGE']

    def init_flowermons_pokedex(self, flowermons_filename):
        with open(flowermons_filename, 'r', encoding = "utf8") as flowermons_file:
            for line in flowermons_file.readlines():
                FLOWERMONS_POKEDEX.add(line.strip().lower())

    def load_flowermons_user_data(self, flowermons_user_data_filename):
        if os.path.exists(flowermons_user_data_filename):
            with open(flowermons_user_data_filename, 'r', encoding = "utf8") as flowermons_user_data_file:
                for line in flowermons_user_data_file.readlines():
                    data = list(map(lambda x: x.strip().lower(), line.split('\t')))
                    username = data[0]
                    user_pokemon_stats = FLOWERMONS_USER_POKEDEX.get(username, {})

                    user_pokemon_set = user_pokemon_stats.get('CAUGHT', set())
                    user_pokemon_shiny_set = user_pokemon_stats.get('SHINY', set())

                    user_pokemon_set.add(data[1])
                    if 'SHINY' in line:
                        user_pokemon_shiny_set.add(data[1])
                    user_pokemon_stats['CAUGHT'] = user_pokemon_set
                    user_pokemon_stats['SHINY'] = user_pokemon_shiny_set

                    FLOWERMONS_USER_POKEDEX[username] = user_pokemon_stats

    def on_welcome(self, c, e):
        ''' Handle welcome. '''
        print('Joining channel: %s' % (self.channel), file = OUTPUT_FILE)
        c.cap('REQ', ':twitch.tv/membership')
        c.cap('REQ', ':twitch.tv/tags')
        c.cap('REQ', ':twitch.tv/commands')
        c.join(self.channel)
        print('Successfully joined channel, have at it!')

    def on_pubmsg(self, c, e):
        ''' Handles message in chat. '''

        # give a streamer shoutout if viewer is in the approved streamers set
        # and streamer has not already gotten a shout out
        # (i.e., manual shoutout with !so <username> command)
        self.auto_streamer_shoutout(e)
        user_message = e.arguments[0].encode('ascii', 'ignore').strip().lower().decode("utf-8")
        if user_message in AUTOBOT_RESPONSES.keys():
            self.send_auto_bot_response(user_message)
            return
        cmd_issuer = self.get_username(e)

        # If a chat message starts with an exclamation point, try to run it as a command
        try:
            parsed_args = user_message.split(' ')
        except UnicodeEncodeError:
            print("[UnicodeEncodeError], Error parsing command.", file = ERROR_FILE)
            return
        ##TODO: REPLACE WITH REGEX
        if not parsed_args[0].startswith('!'):
            return
        cmd = parsed_args[0].replace('!','')
        cmd_args = []
        if len(parsed_args) > 1:
            cmd_args = list(map(lambda x: x.replace('@',''), parsed_args[1:]))
        print('Received command: %s with args: %s' % (cmd, ', '.join(cmd_args)), file = OUTPUT_FILE)
        try:
            self.do_command(e, cmd_issuer, cmd, cmd_args)
        except Exception as e:
            print(e, file = OUTPUT_FILE)
        return

    def send_auto_bot_response(self, message):
        '''
            Sends custom response to matching messages in chat.
            Always send response if message startswith '!', otherwise
            randomly decide whether to send response.
        '''
        c = self.connection
        response = response = random.choice(AUTOBOT_RESPONSES[message])
        if message.startswith('!') or random.choice([True, False, False]):
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
        try:
            for d in e.tags:
                if d['key'] in ['subscriber', 'founder']:
                    if d['value'][0] == '1':
                        return True
                elif d['key'] in ['badges', 'badge-info']:
                    if 'founder' in d['value']:
                        return True
        except:
            return False
        return False

# TODO: update to use latest twitch api

    # def get_channel_id(self, twitch_channel):
    #     ''' Returns the twitch channel id. '''
    #     url = 'https://api.twitch.tv/kraken/users?login=' + twitch_channel
    #     headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
    #     r = requests.get(url, headers=headers).json()
    #     return r['users'][0]['_id']

    # def get_last_game_played(self, twitch_channel_id):
    #     ''' Returns last game played for given channel id. '''
    #     url = 'https://api.twitch.tv/kraken/channels/' + twitch_channel_id
    #     headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
    #     r = requests.get(url, headers=headers).json()
    #     try:
    #         game = encode_ascii_string(r['game'])
    #     except:
    #         game = 'None'
    #     return game

    # def is_spawnpoint_team_member(self, twitch_channel_id):
    #     ''' Returns which stream teams a channel belongs to. '''
    #     url = 'https://api.twitch.tv/kraken/channels/' + twitch_channel_id + '/teams'
    #     headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
    #     r = requests.get(url, headers=headers).json()
    #     if 'teams' in r:
    #         for data in r['teams']:
    #             if data.get('name', '').lower() == 'spawnpoint':
    #                 return True
    #     return False

    def current_death_count(self, c):
        ''' Returns current death count. '''
        message = "@%s's current death count is %s" % (self.channel_display_name, self.death_count)
        c.privmsg(self.channel, message)

    # ---------------------------------------------------------------------------------------------
    # STREAMER SHOUTOUT FUNCTIONS
    def is_valid_user(self, user):
        ''' Determines whether user is valid for giving shout outs to or should be ignored. '''
        return (user not in self.ignored_users_list)

    def format_streamer_shoutout_message(self, user):
        message = CUSTOM_USER_SHOUTOUTS.get(user, self.user_shoutout_message_template)
        if MSG_USERNAME_REPLACE_STRING in message:
            message = message.replace(MSG_USERNAME_REPLACE_STRING, user)

        # TODO: update to use latest twitch api
        # if MSG_LAST_GAME_PLAYED_REPLACE_STRING in message:
        #     message = message.replace(MSG_LAST_GAME_PLAYED_REPLACE_STRING, game)
        return encode_ascii_string(message)

    def streamer_shoutout_message(self, user):
        ''' Gives a streamer shoutout in twitch chat. '''
        if not self.is_valid_user(user):
            return

        c = self.connection
        if user == self.channel_display_name:
            c.privmsg(self.channel, 'Jebaited')
            return
        # TODO: update to use latest twitch api
        # cid = self.get_channel_id(user)
        # game = self.get_last_game_played(cid)
        USERS_CHECKED.add(user)
        # TODO: update to use latest twitch api
        # if str(game) != "None" or user in APPROVED_AUTO_SHOUTOUT_USERS:
        if user in APPROVED_AUTO_SHOUTOUT_USERS:
            message = self.format_streamer_shoutout_message(user)
            # TODO: update to use latest twitch api
            # if self.is_spawnpoint_team_member(cid):
            #     message = 'Is that a Spawn Point team member I see?! xcornfPOG ' + message
            c.privmsg(self.channel, message)
        else:
            message = self.format_streamer_shoutout_message(user)
            # TODO: update to use latest twitch api
            # if self.is_spawnpoint_team_member(cid):
            #     message = 'Is that a Spawn Point team member I see?! xcornfPOG ' + message
            c.privmsg(self.channel, message)
        if user in SFX_MAPPINGS.keys():
            sfx_filename = os.path.join(self.sfx_directory, SFX_MAPPINGS[user])
            playsound(sfx_filename)
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
    # FLOWERMONS

    def determine_shiny_status(self, user_is_sub):
        '''
            Determines the shiny status of a caught pokemon assuming full odds (Masuda) is 1/4096.
            Subscribers have a 1/512 chance of catching a shiny.
        '''
        shiny_index = random.randint(0, 4095) # CoUnTiNg StArTs At ZeRo
        if user_is_sub:
            shiny_index_lower = (0 if ((shiny_index - FLOWERMONS_SUB_SHINY_DENOM) < 0) else (shiny_index - FLOWERMONS_SUB_SHINY_DENOM))
            shiny_index_upper = (4095 if ((shiny_index + FLOWERMONS_SUB_SHINY_DENOM) > 4095) else (shiny_index + FLOWERMONS_SUB_SHINY_DENOM))
            user_index = random.randint(shiny_index_lower, shiny_index_upper)
        else:
            user_index = random.randint(0, 4095)
        return (user_index == shiny_index)

    def format_flowerdex_check_message(self, cmd_issuer, user_is_sub):
        user_pokemon_stats = FLOWERMONS_USER_POKEDEX.get(cmd_issuer, {})
        user_pokemon_set = user_pokemon_stats.get('CAUGHT', set())
        user_pokemon_shiny_set = user_pokemon_stats.get('SHINY', set())

        if len(user_pokemon_set) > 0:
            message = '@%s your FlowerDex is %s%% complete' % (cmd_issuer, self.calculate_flowerdex_completion(cmd_issuer))
            if len(user_pokemon_shiny_set) > 0:
                if len(user_pokemon_shiny_set) == 1:
                    message = message + ' (%s shiny caught!) ' % (len(user_pokemon_shiny_set))
                else:
                    message = message + ' (%s shinies caught!) ' % (len(user_pokemon_shiny_set))
            message = message + ' and you have %s Flowerballs left!' % (self.get_users_pokeball_count(cmd_issuer, user_is_sub))
        else:
            message = '@%s you have not caught any pokemon yet :(' % (cmd_issuer)
        return message

    def check_flowerdex(self, cmd_issuer, user_is_sub):
        c = self.connection
        c.privmsg(self.channel, self.format_flowerdex_check_message(cmd_issuer, user_is_sub))
        return

    def calculate_flowerdex_completion(self, cmd_issuer):
        user_pokemon_stats = FLOWERMONS_USER_POKEDEX.get(cmd_issuer, {})
        caught_mons = user_pokemon_stats.get('CAUGHT', set())
        return round((100 * len(caught_mons) / len(FLOWERMONS_POKEDEX)), 1)

    def catch_flowermon(self, cmd_issuer, user_is_sub):
        ''' Catches random pokemon for user and stores mon in flowerdex. '''
        c = self.connection
        pokeballs = self.get_users_pokeball_count(cmd_issuer, user_is_sub)
        if pokeballs <= 0:
            c.privmsg(self.channel, '@%s, you do not have any flowerballs left! BibleThump' % (cmd_issuer))
            return
        pokemon = random.choice(list(FLOWERMONS_POKEDEX))
        shiny_status = self.determine_shiny_status(user_is_sub)
        self.store_caught_pokemon(cmd_issuer, pokemon, shiny_status)

        FLOWERMONS_USER_POKEBALLS[cmd_issuer] = pokeballs - 1
        shiny_message = ''
        if shiny_status:
            shiny_message = ' and it was * SHINY * !!!'
        message = '@%s caught %s%s! %s' % (cmd_issuer, pokemon.title(), shiny_message, self.format_flowerdex_check_message(cmd_issuer, user_is_sub))
        try:
            try:
                if shiny_status:
                    shiny_filename = os.path.join(self.sfx_directory, SFX_MAPPINGS['shiny'])
                    playsound(shiny_filename)
            except Exception as e:
                print(e, file = OUTPUT_FILE)
                print('Failed to play shiny sound', file = OUTPUT_FILE)
            c.privmsg(self.channel, message)
        except Exception as e:
            print(e, file = OUTPUT_FILE)
            print(message, file = OUTPUT_FILE)
            c.privmsg(self.channel, 'whoops BibleThump @%s broke me snowpoNK' % (cmd_issuer))
        return

    def store_caught_pokemon(self, cmd_issuer, pokemon, shiny_status):
        ''' Stores pokemon in data file for user. '''
        user_pokemon_stats = FLOWERMONS_USER_POKEDEX.get(cmd_issuer, {})
        user_pokemon_set = user_pokemon_stats.get('CAUGHT', set())
        user_pokemon_shiny_set = user_pokemon_stats.get('SHINY', set())

        user_pokemon_set.add(pokemon)
        if shiny_status:
            user_pokemon_shiny_set.add(pokemon)

        user_pokemon_stats['CAUGHT'] = user_pokemon_set
        user_pokemon_stats['SHINY'] = user_pokemon_shiny_set
        FLOWERMONS_USER_POKEDEX[cmd_issuer] = user_pokemon_stats
        self.update_flowermons_user_pokedex_data_file()

    def update_flowermons_user_pokedex_data_file(self):
        ''' Updates Flowermons user data file. '''
        with open(self.flowermons_user_data_filename, 'w') as flowermons_user_data_file:
            for user, user_pokemon_stats in FLOWERMONS_USER_POKEDEX.items():
                user_pokemon_set = user_pokemon_stats['CAUGHT']
                user_pokemon_shiny_set = user_pokemon_stats['SHINY']
                for pokemon in user_pokemon_set:
                    shiny_status = ('SHINY' if pokemon in user_pokemon_shiny_set else '')
                    flowermons_user_data_file.write('%s\t%s\t%s\n' % (user, pokemon, shiny_status))

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
        FLOWERMONS_USER_POKEBALLS[username] = math.ceil( current_num_balls + balls_purchased + bonus_balls)
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

    def splat3_reveal_day_count(self):
        # reveal_date = datetime.strptime('2/17/2021', '%m/%d/%Y')
        release_date = datetime.strptime('9/9/2022', '%m/%d/%Y')
        today = datetime.strptime(date.today().strftime('%m/%d/%Y'), '%m/%d/%Y')
        days_togo = release_date - today
        c = self.connection
        c.privmsg(self.channel, "xcornfETTI xcornfUN xcornfETTI ONLY %s days UNTIL SPLATOON 3 ARRIVES xcornfETTI xcornfUN xcornfETTI" % days_togo.days)
        return

    # ---------------------------------------------------------------------------------------------
    # BOT MAIN
    def do_command(self, e, cmd_issuer, cmd, cmd_args):
        c = self.connection
        user_has_mod_privileges = False
        if self.user_is_mod(e) or cmd_issuer in self.trusted_users_list:
            user_has_mod_privileges = True
        user_is_sub = True #self.user_is_sub(e)

        if cmd == 'splat3':
            self.splat3_reveal_day_count()
        elif cmd == 'death':
            self.current_death_count(c)
        elif cmd == 'flowermons':
            c.privmsg(self.channel, 'The Flowermons help doc can be found here: https://github.com/xcornflowerx/flowerbot/blob/master/docs/Flowermons.md')
            c.privmsg(self.channel, 'Flowermons commands list: !catch !flowerdex !leaders')
        elif cmd in ['flowerdex', 'catch', 'addballs', 'leaders'] and self.flowermons_enabled:
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
        elif cmd == 'deathadd' and user_has_mod_privileges:
            self.death_count += 1
            c.privmsg(self.channel, "%s's current death count is now %s BibleThump" % (self.channel_display_name, self.death_count))
        elif cmd == 'deathreset' and user_has_mod_privileges:
            self.death_count = 0
            c.privmsg(self.channel, "%s reset their current death count" % (self.channel_display_name))
        elif cmd == 'deathinit' and user_has_mod_privileges:
            self.death_count = int(cmd_args[0])
            c.privmsg(self.channel, "%s initialized their current death count to %s" % (self.channel_display_name, self.death_count))
        elif cmd == "so" and len(cmd_args) > 0 and user_has_mod_privileges:
            self.streamer_shoutout_message(cmd_args[0])
        elif cmd == "streameraddnew" and cmd_issuer == self.channel_display_name:
            self.update_approved_auto_shoutout_users_list(cmd_args[0])

def usage(parser):
    print(parser.print_help(), file = OUTPUT_FILE)
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
        print('\nBye!', file = OUTPUT_FILE)
