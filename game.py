#! /usr/bin/python

import math, random, time, Queue
import curses, curses.wrapper

colors = [chr(i) for i in xrange(9)]
gray, blue, green, red, purple, teal, yellow, foggy, player_color = colors

__ = gray + " "

class Thing:
	THING_STRINGS = [
		__ + yellow + "g",
		teal + "e" + __,
	]
	GOLD = 0
	ENEMY = 1
	def __init__(self, basic):
		self.basic = basic

	def to_string(self):
		return self.THING_STRINGS[self.basic]

class Tile:
	TILE_STRINGS = [
		__ + __,
		gray+"\xff"+gray+"\xff",
		red+"\xff"+red+"\xff",
		green+"?"+green+"?",
		teal+"\\"+__,
		teal+"/"+__,
		gray+"_"+__,
		purple+"M"+purple+"M",
		blue+"\xff"+blue+"\xff",
	]
	BLANK = 0
	WALL = 1
	EDGE = 2
	DOOR = 3
	START = 4
	DESTINATION = 5
	ROOM = 6
	MAGIC_BARRIER = 7
	GLASS = 8

	def __init__(self, basic):
		# Store the basic type of the tile
		self.basic = basic
		self.contents = []
		# Some type dependent storage.
		self.steps_skipped = None

	def to_string(self):
		if self.basic == self.DOOR:
			# Return a letter based on the door's value.
			for bound, symbol in ((150, green+"D"+green+"D"), (0, green+"d"+green+"d")):
				if self.steps_skipped >= bound:
					return symbol
		return self.TILE_STRINGS[self.basic]

	def is_passable(self, doors_count=True):
		# Reject the door types if doors don't count.
		if self.basic in [self.DOOR, self.MAGIC_BARRIER] and not doors_count:
			return False
		return self.basic in [self.BLANK, self.DOOR, self.ROOM, self.MAGIC_BARRIER, self.START, self.DESTINATION]

	def is_transparent(self):
		return self.basic in [self.BLANK, self.ROOM, self.GLASS, self.START, self.DESTINATION]

item_class_list = []
def item(cls):
	item_class_list.append(cls)
	return cls

class ItemType:
	name = "???"
	description = "A non-descript item."
	usable = False
	directional = False
	magical = False
	greater = False
	value = 0

	def use(self):
		extra = {}
		if self.directional:
			direction = get_direction()
			# Cancel the usage, if no direction was provided.
			if direction is None:
				return False
			extra["direction"] = direction
		return self.activate(**extra)

@item
class ItemKey(ItemType):
	name = "key"
	long_name = "Key"
	description = "A small key, plain key."
	usable = True
	directional = True
	value = 5

	def activate(self, direction=None):
		# See if there's a door next to the player.
		tile = w.cells[w.player.get_in_direction(direction)]
		if tile.basic == Tile.DOOR or (self.magical and tile.basic == Tile.MAGIC_BARRIER):
			if tile.basic == Tile.DOOR:
				show_message("The key unlocks the door!")
			else:
				show_message("The key dissolves the magical barrier!")
			tile.basic = Tile.BLANK
			return True

@item
class ItemMagicalKey(ItemKey):
	name = "m-key"
	long_name = "Magical Key"
	description = "A purple glowing key."
	magical = True
	value = 50

@item
class ScrollOfSeeing(ItemType):
	name = "s-seeing"
	long_name = "Scroll of Seeing"
	description = "A blue scroll that allows you to see around corners."
	value = 10

	def activate(self):
		locations = set((w.player.xy,))
		# Propagate vision a number of rounds.
		# Run 2 rounds, except greater version gets run 3 rounds.
		for rounds in xrange(2 + self.greater):
			next_locations = set()
			for xy in locations:
				if w.cells[xy].is_transparent():
					next_locations |= set(i for i in w.visible_set(xy))
			locations = next_locations
			for xy in locations:
				if not w.cells[xy].is_transparent(): continue
				w.print_pattern(xy, blue+"\xff"+blue+"\xff")
			stdscr.refresh()
			time.sleep(0.4)
		w.revealed |= locations
		w.dirty |= locations
		return True

@item
class GreaterScrollOfSeeing(ScrollOfSeeing):
	name = "gs-seeing"
	long_name = "Greater Scroll of Seeing"
	description = "A large blue scroll that allows you to see far around corners."
	greater = True 
	value = 35

@item
class ScrollOfRevelation(ItemType):
	name = "s-reveal"
	long_name = "Scroll of Revelation"
	description = "A green scroll that allows you to see through walls."
	value = 30

	def activate(self):
		radius = 10 + self.greater * 5
		already_hit = set()
		for r in xrange(radius):
			w.pprint()
			for dx in xrange(-radius, radius+1):
				x = w.player.xy[0] + dx
				for dy in xrange(-radius, radius+1):
					y = w.player.xy[1] + dy
					xy = x, y
					if xy not in w.cells: continue
					if (dx**2 + dy**2)**0.5 <= r and xy not in already_hit:
						w.print_pattern(xy, green+"\xff"+green+"\xff")
						w.revealed.add(xy)
						w.dirty.add(xy)
						already_hit.add(xy)
			stdscr.refresh()
			time.sleep(0.1)
		return True

@item
class GreaterScrollOfRevelation(ScrollOfRevelation):
	name = "gs-reveal"
	long_name = "Greater Scroll of Revelation"
	description = "A large green scroll that allows you to see far through walls."
	greater = True
	value = 100

@item
class ScrollOfTeleportation(ItemType):
	name = "s-teleport"
	long_name = "Scroll of Teleportation"
	description = "A small yellow scroll that transports the user to undiscovered territory. Be careful what you land on!"
	value = 85

	def activate(self):
		if self.greater:
			# If scroll is greater, then you can teleport directly to anywhere you want.
			result = get_location_selection("Teleport where?", lambda xy: (2 <= xy[0] < w.w-2) and (2 <= xy[1] < w.h-2))
			# Check if the user canceled the teleport.
			if not result:
				return False
			dest_x, dest_y = result
		else:
			# If the scroll is not greater, try to jump to an unrevealed location.
			dest_options = set()
			for x in xrange(2, w.w-2):
				for y in xrange(2, w.h-2):
					if (x, y) not in w.revealed:
						dest_options.add((x, y))
			if dest_options:
				dest_x, dest_y = random.choice(list(dest_options))
			else:
				# If no tiles are unrevealed, then simply choice randomly.
				dest_x, dest_y = random.randrange(2, w.w-2), random.randrange(2, w.h-2)
		for dx in (-1, 0, 1):
			for dy in (-1, 0, 1):
				if abs(dx) + abs(dy) > 1: continue
				xy = (dest_x+dx, dest_y+dy)
				w.print_pattern(xy, yellow+"\xff"+yellow+"\xff")
				w.revealed.add(xy)
				w.dirty.add(xy)
		stdscr.refresh()
		time.sleep(0.4)
		w.pprint()
		stdscr.refresh()
		time.sleep(1.0)
		for dx in (-1, 0, 1):
			for dy in (-1, 0, 1):
				if abs(dx) + abs(dy) > 1: continue
				w.cells[dest_x+dx, dest_y+dy] = Tile(Tile.BLANK)
		w.dirty.add(w.player.xy)
		w.player.xy = dest_x, dest_y
		return True

@item
class GreaterScrollOfTeleportation(ScrollOfTeleportation):
	name = "gs-teleport"
	long_name = "Greater Scroll of Teleportation"
	description = "A yellow scroll that transports the user. Be careful what you land on!"
	value = 450
	greater = True

@item
class AnkhOfRetreat(ItemType):
	name = "retreat"
	long_name = "Ankh of Retreat"
	description = "Break in case of emergency."
	value = 120

	def activate(self):
		while True:
			result = get_location_selection("Retreat where?", lambda xy: xy in w.revealed)
			if not result: # Handle action cancelation.
				return False
			# Simultaneously disallow teleporting into magical areas and walls.
			# Equivalently: You can only teleport where you could walk.
			if result not in w.steps_doors_dont_count:
				show_message("Cannot retreat to a magical area or into walls.")
				continue
			break
		w.dirty.add(w.player.xy)
		w.player.xy = result
		return True

@item
class ScryingOrb(ItemType):
	name = "scry"
	long_name = "Scrying Orb"
	description = "A pale blue orb, filled with mists."
	value = 80

	def activate(self):
		result = get_location_selection("Scry where?", lambda xy: True)
		w.see_from(result)
		return True

@item
class BlinkPowder(ItemType):
	name = "blink"
	long_name = "Blink Powder"
	description = "Sprinkling a little of this dust lets you jump about within eye-sight."
	value = 60

	def activate(self):
		while True:
			result = get_location_selection("Blink where? (Must be within eye-sight.)", lambda xy: w.check_line_of_sight(w.player.xy, xy))
			if not result: # Check for action cancelation.
				return False
			if not w.cells[result].is_passable(doors_count=False):
				show_message("Can only blink to passable terrain.")
				continue
			break
		w.dirty.add(w.player.xy)
		w.player.xy = result
		return True

@item
class DemolitionWand(ItemType):
	name = "demo"
	long_name = "Demolition Wand"
	description = "Breaks down some walls."
	directional = True
	value = 300

	def activate(self, direction=None):
		tile = w.cells[w.player.get_in_direction(direction)]
		if tile.basic in (Tile.WALL, Tile.DOOR, Tile.GLASS):
			tile.basic = Tile.BLANK
			return True
		return False

class Player:
	def __init__(self):
		self.xy = None
		self.inventory = {}
		# For debugging, give the play 50 of every item.
		for item in item_class_list:
			self.inventory[item()] = 50

	def lookup_item(self, name):
		for itemtype, count in self.inventory.iteritems():
			pass

	def use_item(self, name):
		for itemtype, count in self.inventory.iteritems():
			if itemtype.name == name and count > 0:
				break
		else:
			# Item not found, or you don't have enough.
			show_message("No matching item: %r" % name)
			return False
		success = itemtype.use()
		if success:
			self.inventory[itemtype] -= 1
		else:
			show_message("No effect.")

	def get_in_direction(self, direction_code):
		delta = direction_mapping[direction_code]
		return self.xy[0] + delta[0], self.xy[1] + delta[1]

# Some global computations.
cut_patterns = []
chest_patterns = []
for index in (1, 3, 5, 7):
	pattern = [True]*9
	pattern[4] = False
	pattern[index] = False
	cut_patterns.append(pattern)
	chest_patterns.append([not i for i in pattern])
direction_mapping = {ord("w"): (0, -1), ord("a"): (-1, 0), ord("s"): (0, 1), ord("d"): (1, 0)}

class World:
	GAP_PROPORTION    = 0.07
	DOOR_PROPORTION   = 0.2
	GOLD_PROPORTION   = 0
	ROOM_PROPORTION   = 0.035
	GLASS_PROPORTION  = 0.05
	# Eliminate doors that only get rid of at most this many steps.
	DOOR_THRESHOLD    = 50
	ROOMS_MADE_OF     = Tile.EDGE
	ROOM_SIZES        = (3, 5, 7, 9)
	GLASS_WALL_LENGTH = 5
	# Whether Tile.EDGE blocks can be trimmed.
	CORNER_CUT_ROOMS  = False
	# Trim back super zig zaggy walls.
	TRIM_OPERATIONS = [
		(cut_patterns, Tile, Tile.BLANK, 1.0),
		(cut_patterns, Tile, Tile.BLANK, 1.0),
		(chest_patterns, Thing, Thing.GOLD, 0.65),
	]
	# This is the probability that a nether crack will spawn in a magical area
	# if at least one magical area exists on the border.
	NETHER_CRACK_PROBABILITY = 0.5
	# For an enemy candidate location that can see x tiles the probability of spawning is:
	#   1 - (1 - ENEMY_PROBABILITY) * e**(-x/ENEMY_TILE_CONSTANT)
	ENEMY_PROBABILITY = 0.25
	ENEMY_TILE_CONSTANT = 40

	# Debugging rendering features.
	print_steps = False
	print_paths = False

	def __init__(self, w, h):
		# XXX: DEBUG, GET RID OF LATER
		self.steps_doors_dont_count, self.steps = {}, {}

		# Generate the initial maze via a random depth first search.
#P#		print "Generating maze."
		self.cells = {}
		self.w, self.h = 2*w+1, 2*h+1
		# Place the outermost border of Tile.EDGE tiles.
		edge_locs = []
		for x in xrange(self.w):
			edge_locs.append((x, 0))
			edge_locs.append((x, self.h-1))
		for y in xrange(1, self.h-1):
			edge_locs.append((0, y))
			edge_locs.append((self.w-1, y))
		for xy in edge_locs:
			self.cells[xy] = Tile(Tile.EDGE)
		for x in xrange(1, self.w-1):
			for y in xrange(1, self.h-1):
				self.cells[x, y] = Tile(Tile.WALL)
		#self.start_loc = self.random_center()
		self.start_loc = (1, 1)
		stack = [(None, self.start_loc)]
		while stack:
			prev, loc = stack.pop()
			if self.cells[loc].basic == Tile.BLANK:
				continue
			if prev is not None:
				self.cells[(prev[0]+loc[0])/2, (prev[1]+loc[1])/2] = Tile(Tile.BLANK)
			self.cells[loc] = Tile(Tile.BLANK)
			neighbors = self.get_neighbors(loc)
			neighbors = [n for n in neighbors if self.cells[n].basic == Tile.WALL and self.cells[n[0]*2-loc[0], n[1]*2-loc[1]].basic == Tile.WALL]
			random.shuffle(neighbors)
			for n in neighbors:
				stack.append((loc, (n[0]*2-loc[0], n[1]*2-loc[1])))
		# At this point the maze is a tree.
		# Add some random gaps.
#P#		print "Placing cracks and rooms."
		for i in xrange(int(self.GAP_PROPORTION * w * h)):
			xy = self.random_wall()
			# Make sure the wall isn't fully surrouneded, or we would (trivially) disconnect the graph!
			# This is important!
			if any(self.cells[n].basic == Tile.BLANK for n in self.get_neighbors(xy)):
				self.cells[xy] = Tile(Tile.BLANK)
		# Add some rooms.
		for i in xrange(int(self.ROOM_PROPORTION * w * h)):
			room_w, room_h = random.choice(self.ROOM_SIZES), random.choice(self.ROOM_SIZES)
			xy = random.choice(range(1, self.w-room_w, 2)), random.choice(range(1, self.h-room_h, 2))
			for x in xrange(room_w):
				for y in xrange(room_h):
					self.cells[xy[0]+x, xy[1]+y] = Tile(Tile.ROOM)
			# Find all the borders to the room.
			borders = []
			for x in xrange(-1, room_w+1):
				x += xy[0]
				for y in xrange(-1, room_h+1):
					y += xy[1]
					if self.cells[x, y].basic == Tile.BLANK:
						borders.append((x, y))
					# Upgrade walls around rooms to edges, for that dramatic effect.
					if self.cells[x, y].basic == Tile.WALL:
						self.cells[x, y].basic = self.ROOMS_MADE_OF
			# Randomly close off borders, so long as we maintain connectedness.
			while True:
				random.shuffle(borders)
				for border in borders[:]:
					# See if this modification makes the graph disconnected.
					self.cells[border] = Tile(self.ROOMS_MADE_OF)
					if not self.is_connected():
						# Disallowed, undo.
						self.cells[border] = Tile(Tile.BLANK)
						continue
					# Good, this one is allowed.
					borders.remove(border)
					break
				else: break
		# Do a sanity check, to catch bugs.
		self.assert_connected()
		# Now we start adding objects in other than blanks, walls, and edges.
		# Add some random unlockable doors.
#P#		print "Placing doors."
		self.doors = []
		for i in xrange(int(self.DOOR_PROPORTION * w * h)):
			xy = self.random_wall()
			# Make sure the spot makes sense for a door.
			neighbors = self.get_neighbors(xy)
			occupancy = [self.cells[n].basic == Tile.WALL for n in neighbors]
			if occupancy in ([True, True, False, False], [False, False, True, True]):
				door = self.cells[xy] = Tile(Tile.DOOR)
				# Store the coordinates of the two sides of the door, while it's easy.
				door.sides = [n for n in neighbors if self.cells[n].basic != Tile.WALL]
				self.doors.append(door)
		# Cut corners, to make minirooms.
		# Also, place treasure chests in corners.
#P#		print "Trimming walls, placing chests."
		for pattern_set, factory, arg, probability in self.TRIM_OPERATIONS:
			to_change = []
			for x in xrange(1, self.w-1):
				for y in xrange(1, self.h-1):
					# Determine the neighbor pattern.
					neighbors = self.get_von_neumann_neighbors((x, y))
					occupancy = [self.cells[n].is_passable(doors_count=False) for n in neighbors]
					if occupancy in pattern_set and (self.cells[x, y].basic != Tile.EDGE or self.CORNER_CUT_ROOMS):
						to_change.append((x, y))
			for xy in to_change:
				if random.random() > probability: continue
				if factory == Tile:
					self.cells[xy] = factory(arg)
				elif factory == Thing:
					self.cells[xy].contents.append(factory(arg))
#P#		print "Placing special elements."
		# Place some glass walls.
		for i in xrange(int(self.GLASS_PROPORTION * w * h)):
			loc = self.random_wall()
			stack = [loc]
			already_hit = set()
			while stack and len(already_hit) < self.GLASS_WALL_LENGTH:
				xy = stack.pop()
				# Only convert walls into glass.
				if self.cells[xy].basic != Tile.WALL: continue
				if xy in already_hit: continue
				already_hit.add(xy)
				self.cells[xy].basic = Tile.GLASS
				for n in self.get_neighbors(xy):
					stack.append(n)
		# Compute a map of how many steps are required to walk to each point on the map.
		# Compute twice, once with doors not counting, once with them counting.
		# The doors not counting map will tell us the value of each door.
		# However, we still use the door counting map for most other purposes.
		# Because realistically the player can take a lot of doors.
		results = [{}, {}]
		for doors_count in (False, True):
			steps = results[doors_count]
			queue = Queue.Queue()
			queue.put((self.start_loc, 0))
			while not queue.empty():
				loc, count = queue.get()
				if loc in steps:
					continue
				steps[loc] = count
				neighbors = self.get_neighbors(loc)
				neighbors = [n for n in neighbors if self.cells[n].is_passable(doors_count=doors_count)]
				for n in neighbors:
					queue.put((n, count+1))
		# Name the results we computed.
		self.steps_doors_dont_count, self.steps = results
		# Make the destination be the furthest away point, not using doors.
		# If you instead count doors then the destination selection tends to make doors useless.
		self.dest_loc = max(self.steps_doors_dont_count.keys(), key=self.steps_doors_dont_count.get)
		self.cells[self.dest_loc] = Tile(Tile.DESTINATION)
		self.cells[self.start_loc] = Tile(Tile.START)
		# Compute the value of each door, in terms of how many steps it saves.
		for door in self.doors:
			# If one side of the door isn't in steps_doors_dont_count,
			# then it means that the door passes into a special only doors allowed section.
			# This is quite rare! Mark the door as a magical barrier.
			flag = 0
			for xy in door.sides:
				if xy not in self.steps_doors_dont_count:
					door.basic = Tile.MAGIC_BARRIER
					flag += 1
			if flag == 2:
				# Eliminate doors that go within a magical area.
				# We blank them out, so magical areas are a little sparser
				door.basic = Tile.BLANK
			if flag: continue
			side_values = [self.steps_doors_dont_count[xy] for xy in door.sides]
			door.steps_skipped = max(side_values) - min(side_values)
			# Delete the door if it's too useless.
			if door.steps_skipped < self.DOOR_THRESHOLD:
				door.basic = Tile.WALL
		# Add random goodies.
		# Rule: Better goodies appear in high step count regions.
		for obj, prob in [(Thing.GOLD, self.GOLD_PROPORTION)]:
			for i in xrange(int(prob * w * h)):
				xy = self.random_tile()
				if self.cells[xy].basic == Tile.BLANK:
					self.cells[xy].contents.append(Thing(obj))
		# Add enemies, based on a simple algorithm:
		# Compute the number of tiles visible from each open tile. Place an enemy at the
		# tile that can see the most. Now, disqualify every tile visible from that tile.
		# Repeat until the queue is empty. This guarantees that large regions have an enemy
		# near the middle. It also guarantees that enemies are always spawned being unable
		# to see each other. The difficulty of an enemy scales as the step count. The type
		# of the enemy is scaled by the number of visible tiles. For example, high difficulty
		# low tile count spawns traps, while high tile count spawns boss enemies, because
		# it's likely to be in the middle of a room.
#P#		print "Finding visibility map."
		visible_count = {}
#		for x in xrange(self.w):
#			for y in xrange(self.h):
#				# Only consider passible squares.
#				if self.cells[x, y].is_passable(doors_count=False):
#					visible_count[x, y] = len(self.visible_set((x, y)))
		# Disqualify tiles adjacent to the origin.
		def disqualify_from(spot):
			for xy in self.visible_set(spot):
				if xy in visible_count:
					visible_count.pop(xy)
		disqualify_from(self.start_loc)
#P#		print "Populating monsters."
		while visible_count:
			# Now, find the most visible tile.
			spot = max(visible_count, key=visible_count.get)
			visible_tiles = visible_count[spot]
			# Only spawn the enemy with a probability that goes up with the number of visible tiles.
			probability = 1.0 - (1.0 - self.ENEMY_PROBABILITY) * math.e**(-visible_tiles/float(self.ENEMY_TILE_CONSTANT))
			if random.random() <= probability:
				self.cells[spot].contents.append(Thing(Thing.ENEMY))
			# Find the visibility set of the new enemy, and eliminate those tiles.
			disqualify_from(spot)
		# Place extremely rare stuff, like nether cracks.
#P#		print "Placing rare objects and world elements."
		# Spawn a nether crack: A cell on the border that is a Tile.WALL tile.
		# If the user uses any of the available means of breaking down walls, this
		# will result in a gap off the map, allowing the user to enter the nether.
		# Nether cracks can only spawn in magical areas, so find all the magical edges.
		magical_edges = []
		for xy in edge_locs:
			for n in self.get_neighbors(xy):
				if n in self.steps and n not in self.steps_doors_dont_count:
					magical_edges.append(xy)
		# Place the nether crack.
		if magical_edges and random.random() <= self.NETHER_CRACK_PROBABILITY:
			self.cells[random.choice(magical_edges)] = Tile(Tile.WALL)
		# Finally, one last connectedness assertion.
		self.assert_connected()
		# Initialize the fog.
		self.revealed = set()
		# Initialize the player.
		self.player = Player()
		self.player.xy = self.start_loc
		# Compute the shortest path, just for debugging sake.
#P#		print "Computing pathing."
		self.shortest_winning_path = self.shortest_path(self.player.xy, self.dest_loc)
		self.shortest_doorless_path = self.shortest_path(self.player.xy, self.dest_loc, doors_count=False)
		# For efficiency rerendering, use a dirty list.
		# Initally, everything is dirty, to require a full first rerender.
		self.full_rerender()

	def full_rerender(self):
		self.dirty = set((x, y) for x in xrange(self.w) for y in xrange(self.h))

	def is_connected(self):
		# Do a simple DFS to see if the world is connected.
		self.reached = set()
		stack = [self.start_loc]
		while stack:
			xy = stack.pop()
			if xy in self.reached: continue
			self.reached.add(xy)
			for n in self.get_neighbors(xy):
				if self.cells[n].is_passable():
					stack.append(n)
		# Check if every passable cell has been touched.
		for xy, tile in self.cells.iteritems():
			if tile.is_passable() and xy not in self.reached:
				return False
		return True

	def assert_connected(self):
		# Guarantee that the graph really is connected.
		if not self.is_connected():
			# Mark every reached cell.
			for xy in self.reached:
				self.cells[xy].basic = Tile.GOLD
			self.pprint()
			print red+"NOT CONNECTED"
			exit()

	def shortest_path(self, a, b, doors_count=True):
		parent = {}
		queue = Queue.Queue()
		queue.put((None, a))
		while not queue.empty():
			prev, xy = queue.get()
			if xy in parent: continue
			parent[xy] = prev
			for n in self.get_neighbors(xy):
				if self.cells[n].is_passable(doors_count=doors_count):
					queue.put((xy, n))
		# Trace back the path
		path = [b]
		while path[-1] is not None:
			path.append(parent[path[-1]])
		return path[-2::-1]

	def check_line_of_sight(self, a, b):
		if a == b: return True
		delta = b[0] - a[0], b[1] - a[1]
		norm = (delta[0]**2.0 + delta[1]**2.0)**0.5
		unit = delta[0]/norm, delta[1]/norm
		for c in xrange(0, int(norm)+1):
			xy = int(a[0] + 0.5 + unit[0] * c), int(a[1] + 0.5 + unit[1] * c)
			if xy == a or xy == b: continue
			if not self.cells[xy].is_transparent():
				return False
		return True

	def visible_set(self, origin):
		stack = [origin]
		reached = set()
		while stack:
			xy = stack.pop()
			if xy in reached or not self.check_line_of_sight(origin, xy):
				continue
			reached.add(xy)
			for n in self.get_neighbors(xy):
				stack.append(n)
				if n not in reached:
					for nn in self.get_neighbors(n):
						stack.append(nn)
		return reached

	def see_from(self, origin):
		for xy in self.visible_set(origin):
			self.revealed.add(xy)
			self.dirty.add(xy)

	def get_neighbors(self, xy):
		return [(xy[0]+i, xy[1]+j) for i, j in ((-1, 0), (1, 0), (0, -1), (0, 1))]

	def get_von_neumann_neighbors(self, xy):
		return [(xy[0]+i, xy[1]+j) for i in (-1, 0, 1) for j in (-1, 0, 1)]

	def random_center(self):
		return (2*random.randrange(0, self.w/2)+1, 2*random.randrange(0, self.h/2)+1)

	def random_tile(self):
		return (random.randrange(1, self.w), random.randrange(1, self.h))

	def random_wall(self):
		return (2*random.randrange(1, self.w/2), 2*random.randrange(1, self.h/2))

	def print_character(self, x, y, desc):
		color, s = desc
		special, attr = 0, curses.color_pair(color_mapping[color])
		if s == "\xff":
			special |= curses.A_ALTCHARSET
			s = curses.ACS_CKBOARD
		if isinstance(s, str): s = ord(s)
		if special:
			stdscr.attron(special)
		stdscr.addch(y, x, s, attr)
		if special:
			stdscr.attroff(special)

	def print_pattern(self, xy, pattern):
		self.print_character(2*xy[0], xy[1], pattern[:2])
		self.print_character(2*xy[0]+1, xy[1], pattern[2:])

	def pprint(self, fog=True):
		def composite(a, b):
			# Compose two characters, with b overlayed on a.
			a1, a2 = a[:2], a[2:]
			b1, b2 = b[:2], b[2:]
			if b1 != __: a1 = b1
			if b2 != __: a2 = b2
			return a1 + a2
		def print_cell(x, y):
			tile = self.cells[x, y]
			s = tile.to_string()
			if (x, y) not in self.revealed:
				return foggy + ":" + foggy + ":"
			# Mark the floors of magical realms.
			if (x, y) not in self.steps_doors_dont_count:
				if s == __ + __:
					s = purple + "." + __
				elif s == gray + "_" + __:
					s = purple + "_" + __
			if self.print_paths:
				if (x, y) in self.shortest_doorless_path:
					s = composite(s, __ + red + "X")
				if (x, y) in self.shortest_winning_path:
					s = composite(s, __ + yellow + "X")
			if self.print_steps and s == __ + __ and (x, y) in self.steps_doors_dont_count:
				s = composite(s, __ + colors[(self.steps_doors_dont_count[x, y]/50)%len(colors)]+".")
			# Layer objects on top.
			for thing in tile.contents:
				s = composite(s, thing.to_string())
			if (x, y) == self.player.xy:
				s = composite(s, player_color + "P" + __)
			return s
		for x, y in self.dirty:
			s = print_cell(x, y)
			self.print_character(2*x, y, s[:2])
			self.print_character(2*x+1, y, s[2:])
		self.dirty = set()
#		stdscr.addstr(y, 0, " ".join(get(x, y) for x in xrange(self.w)))

w = World(35, 18)

def show_message(msg):
	stdscr.addstr(screen_height-1, 0, msg)
	stdscr.getch(0, 0)
	stdscr.addstr(screen_height-1, 0, " "*len(msg))

def get_input(prompt):
	stdscr.addstr(screen_height-1, 0, prompt)
	# Request a string.
	curses.echo()
	curses.curs_set(1)
	string = stdscr.getstr(screen_height-1, len(prompt), 32)
	curses.noecho()
	curses.curs_set(0)
	# Clear out the line.
	stdscr.addstr(screen_height-1, 0, " " * (len(prompt) + 32))
	return string

def get_direction():
	prompt = "Enter a direction. (WASD, esc/enter to cancel)"
	stdscr.addstr(screen_height-1, 0, prompt)
	try:
		while True:
			key = stdscr.getch(0, 0)
			if key in direction_mapping:
				return key
			elif key == 27 or key == 10 or key == 13: 
				return None
	finally:
		stdscr.addstr(screen_height-1, 0, " " * len(prompt))

def get_location_selection(prompt, validator):
	prompt += " (enter confirms/esc cancels)"
	try:
		stdscr.addstr(screen_height-1, 0, prompt)
		curses.curs_set(2)
		xy = w.player.xy
		if not validator(xy):
			# As a hack, if the validator fails on us to start with,
			# try it in the middle of the screen.
			xy = w.w/2, w.h/2
		while True:
			key = stdscr.getch(xy[1], 2*xy[0])
			if key in direction_mapping:
				delta = direction_mapping[key]
				new_xy = xy[0]+delta[0], xy[1]+delta[1]
				if (0 <= new_xy[0] < w.w) and (0 <= new_xy[1] < w.h) and validator(new_xy):
					xy = new_xy
			elif key == 27:
				return False
			elif key == 10 or key == 13:
				return xy
	finally:
		curses.curs_set(0)
		stdscr.addstr(screen_height-1, 0, " " * len(prompt))

def main_loop(_stdscr):
	global stdscr, w, screen_height, screen_width
	stdscr = _stdscr
	screen_height, screen_width = stdscr.getmaxyx()

	while True:
		# Cast player vision.
		w.see_from(w.player.xy)
		# Update the world view.
		w.pprint()
		# Get user input.
		action = stdscr.getch(0, 0)
		# Attempt to process as motion.
		if action in direction_mapping:
			delta = direction_mapping[action]
			new_xy = w.player.xy[0]+delta[0], w.player.xy[1]+delta[1]
			if w.cells[new_xy].is_passable(doors_count=False):
				w.player.xy = new_xy
		elif action == ord("u"):
			# Use item.
			item = get_input("Item to use: ").strip()
			if not item: continue
			w.player.use_item(item)
		elif action == ord("i"):
			# Info on item.
			item = get_input("Info on item: ").strip()
			if not item: continue
			w.player.lookup_item(item)
		elif action == ord("0"):
			w.full_rerender()
			for x in xrange(w.w):
				for y in xrange(w.h):
					w.revealed.add((x, y))
		elif action == ord("9"):
			w.full_rerender()
			w.revealed = set()
		elif action == ord("1"):
			w.full_rerender()
			w.print_paths ^= 1
		elif action == ord("2"):
			w.full_rerender()
			w.print_steps ^= 1
		elif action == ord("3"):
			w = World(35, 18)

#curses.wrapper(main_loop)

try:
	stdscr = curses.initscr()
	curses.start_color()
	color_mapping = {}
	def c(name, fg, bg):
		i = len(color_mapping) + 1
		color_mapping[name] = i
		curses.init_pair(i, fg, bg)
	color_mapping[gray] = 0
	c(blue, curses.COLOR_BLUE, curses.COLOR_BLACK)
	c(green, curses.COLOR_GREEN, curses.COLOR_BLACK)
	c(red, curses.COLOR_RED, curses.COLOR_BLACK)
	c(purple, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
	c(teal, curses.COLOR_CYAN, curses.COLOR_BLACK)
	c(yellow, curses.COLOR_YELLOW, curses.COLOR_BLACK)
	c(foggy, curses.COLOR_BLACK, curses.COLOR_WHITE)
	c(player_color, curses.COLOR_BLACK, curses.COLOR_CYAN)
	curses.noecho()
	curses.cbreak()
	curses.curs_set(0)
	stdscr.keypad(1)
	main_loop(stdscr)
finally:
	curses.nocbreak(); stdscr.keypad(0); curses.echo()
	curses.endwin()

