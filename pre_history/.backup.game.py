#! /usr/bin/python

import random, Queue

colors = ["\033[%i;%im" % (i, j) for i, j in ((0, 2), (0, 34), (0, 32), (0, 31), (0, 35), (0, 36), (1, 33))]
gray, blue, green, red, purple, teal, yellow = colors
normal = "\x1B\x5B\x30\x6D"

class Tile:
	THING_STRING = [" ", gray+"#"+normal, gray+"@"+normal, green+"d"+normal, yellow+"g"+normal, teal+"/"+normal, gray+"_"+normal]
	BLANK = 0
	WALL = 1
	EDGE = 2
	DOOR = 3
	GOLD = 4
	DESTINATION = 5
	ROOM = 6

	def __init__(self, basic):
		# Store the basic type of the tile
		self.basic = basic
		# Some type dependent storage.
		self.steps_skipped = None

	def to_string(self):
		if self.basic == self.DOOR:
			# Return a letter based on the door's value.
			for bound, symbol in ((100, green+"D"+normal), (0, green+"d"+normal)):
				if self.steps_skipped >= bound:
					return symbol
		return self.THING_STRING[self.basic]

	def is_passable(self):
		return self.basic in [self.BLANK, self.DOOR, self.GOLD, self.ROOM]

class World:
	GAP_PROPORTION  = 0.05
	DOOR_PROPORTION = 0.05
	GOLD_PROPORTION = 0*0.1
	ROOM_PROPORTION = 0.005
	DOOR_THRESHOLD  = 50

	def __init__(self, w, h):
		# Generate the initial maze via a random depth first search.
		self.cells = {}
		self.w, self.h = 2*w+1, 2*h+1
		for x in xrange(self.w):
			for y in xrange(self.h):
				self.cells[x, y] = Tile(Tile.EDGE)
		for x in xrange(1, self.w-1):
			for y in xrange(1, self.h-1):
				self.cells[x, y] = Tile(Tile.WALL)
#		self.start_loc = self.random_center()
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
		for i in xrange(int(self.GAP_PROPORTION * w * h)):
			self.cells[self.random_wall()] = Tile(Tile.BLANK)
		# Add some rooms.
		for i in xrange(int(self.ROOM_PROPORTION * w * h)):
			room_radius = random.choice((3, 5))
			xy = random.choice(range(1, self.w-room_radius, 2)), random.choice(range(1, self.h-room_radius, 2))
			for x in xrange(room_radius):
				for y in xrange(room_radius):
					self.cells[xy[0]+x, xy[1]+y] = Tile(Tile.ROOM)
			# Find all the borders to the room.
			borders = []
			for x in xrange(-1, room_radius+1):
				for y in xrange(-1, room_radius+1):
					if self.cells[x, y].basic == Tile.BLANK:
						borders.append((x, y))
			# Randomly close off borders, so long as we maintain connectedness.
			while True:
				random.shuffle(borders)
				for border in borders:
					# See if this modification makes the graph disconnected.
					self.cells[border] = Tile.EDGE
					
		# Now we start adding objects in other than blanks, walls, and edges.
		# Add some random unlockable doors.
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
				neighbors = [n for n in neighbors if self.cells[n].is_passable() and (self.cells[n].basic != Tile.DOOR or doors_count)]
				for n in neighbors:
					queue.put((n, count+1))
		# Name the results we computed.
		self.steps_doors_dont_count, self.steps = results
		# Make the destination be the furthest away point, not using doors.
		# If you instead count doors then the destination selection tends to make doors useless.
		self.dest_loc = max(self.steps_doors_dont_count.keys(), key=self.steps_doors_dont_count.get)
		self.cells[self.dest_loc] = Tile(Tile.DESTINATION)
		# Compute the value of each door, in terms of how many steps it saves.
		for door in self.doors:
			side_values = [self.steps_doors_dont_count[xy] for xy in door.sides]
			door.steps_skipped = max(side_values) - min(side_values)
			# Delete the door if it's too useless.
			if door.steps_skipped < self.DOOR_THRESHOLD:
				door.basic = Tile.WALL
		# Add other objects.
		for obj, prob in [(Tile.GOLD, self.GOLD_PROPORTION)]:
			for i in xrange(int(prob * w * h)):
				xy = self.random_tile()
				if self.cells[xy].basic == Tile.BLANK:
					self.cells[xy] = Tile(obj)

	def is_connected(self):
		# Do a simple DFS to see if the world is connected.
		reached = set()
		stack = [self.start_loc]
		while stack:
			xy = stack.pop()
			if xy in reached: continue
			reached.add(xy)
			for n in self.get_neighbors(xy):
				if self.cells[n].is_passable():
					stack.append(n)
		# Check if every passable cell has been touched.
		for xy, tile in self.cells.iteritems():
			if tile.is_passable() and xy not in reached:
				return False
		return True

	def get_neighbors(self, xy):
		return [(xy[0]+i, xy[1]+j) for i, j in ((-1, 0), (1, 0), (0, -1), (0, 1))]

	def random_center(self):
		return (2*random.randrange(0, self.w/2)+1, 2*random.randrange(0, self.h/2)+1)

	def random_tile(self):
		return (random.randrange(1, self.w), random.randrange(1, self.h))

	def random_wall(self):
		return (2*random.randrange(1, self.w/2), 2*random.randrange(1, self.h/2))

	def pprint(self, print_steps=True):
		def get(x, y):
			s = self.cells[x, y].to_string()
			if (x, y) == self.start_loc:
				return teal+"S"+normal
			if print_steps and s == " " and (x, y) in self.steps:
				s = colors[(self.steps_doors_dont_count[x, y]/50)%len(colors)]+"."+normal
			return s
		for y in xrange(self.h):
			print " ".join(get(x, y) for x in xrange(self.w))

w = World(35, 18)
w.pprint()

