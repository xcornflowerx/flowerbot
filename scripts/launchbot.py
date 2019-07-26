import sys
import os
import subprocess

# ---------------------------------------------------------------------------------------------
# globals
OUTPUT_FILE = sys.stdout
ERROR_FILE = sys.stderr

def main():
    FLOWERBOT_HOME = os.getenv('FLOWERBOT_HOME')
    if not FLOWERBOT_HOME or not os.path.isdir(FLOWERBOT_HOME):
        print >> ERROR_FILE, 'Could not resolve path for FLOWERBOT_HOME - please check that this variable exists in sys environment!'
        sys.exit(2)

    script_call = 'python %s/scripts/flowerbot.py --properties-file %s/resources/bot.properties' % (FLOWERBOT_HOME, FLOWERBOT_HOME)
    status = subprocess.call(script_call, shell = True)

if __name__ == '__main__':
    main()
