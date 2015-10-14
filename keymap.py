"""
keymap.py: Handle keyboard command mappings.

Keyboard mappings are read from a file (named 'keyboard_mappings'). Each line looks like:
cmd = key
Comments start with a #, and extraneous whitespace is okay.
key should be a single character, except it may be surrounded by quotes. (This is useful for space/tab.)
"""

keymap = dict()
with open("keyboard_mappings",'r') as f:
	for line in f:
		if line[0] == "#" or len(line.strip()) == 0: continue
		cmd, key = line.split('=',1)
		key = key.strip()
		if len(key) == 3 and key[0] == key[2] == "\"":
			key = key[1]
		keymap[cmd.strip()] = ord(key)