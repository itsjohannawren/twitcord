#!/usr/bin/env python3

def __virtualenv ():
	import os
	import pathlib
	import site
	import sys

	# ----

	DEFAULT_ASCEND = "0"

	# ----

	venv_verbose = os.environ.get ("VENV_VERBOSE", "0")
	if venv_verbose.lower () in ["y", "yes", "true", "on", "1"]:
		venv_verbose = True
	else:
		venv_verbose = False

	# ----

	def vprint (*args, force:bool = False, **kwargs):
		if venv_verbose is True or force is True:
			print ("VENV: ", file = sys.stderr, end = "", **kwargs)
			print (*args, file = sys.stderr, **kwargs)

	# ----

	venv_ascend = os.environ.get ("VENV_ASCEND", DEFAULT_ASCEND)
	try:
		venv_ascend = int (venv_ascend)
	except ValueError:
		vprint ("Invalid value for VENV_ASCEND: Must be base10 integer", force = True)
		venv_ascend = 0

	if venv_ascend < 0:
		venv_ascend = -1

	# ----

	# Start searching using the path to the directory containing this file
	try:
		base_dir = pathlib.Path (__file__).parent.resolve ()
	except NameError:
		base_dir = pathlib.Path ().absolute ()

	while True:
		if (base_dir / "pyvenv.cfg").is_file () and (base_dir / "bin" / "activate").is_file ():
			vprint (f"Found virtual environment: {base_dir}")

			# Pretty straight-forward
			bin_dir = base_dir / "bin"

			# Prepend virtual environment's bin directory to PATH
			os.environ ["PATH"] = os.pathsep.join ([str (bin_dir)] + os.environ.get ("PATH", "").split (os.pathsep))
			# Save the base pat of the virtual environment to VIRTUAL_ENV
			os.environ ["VIRTUAL_ENV"] = str (base_dir)

			# Save the number of sys.path items so it can be re-ordered after additions are made
			prev_length = len (sys.path)

			# Add each package directory to the site so libraries can be found
			for lib_path in [base_dir / "lib" / ("python%i.%i" % sys.version_info [0:2]) / "site-packages"]:
				vprint (f"Adding package directory: {lib_path}")
				site.addsitedir (path.decode ("utf-8") if "" else str (lib_path))

			# Move newly added package directories to the beginning of sys.path
			sys.path [:] = sys.path [prev_length:] + sys.path [0:prev_length]

			# Save the current sys.prefix
			sys.real_prefix = sys.prefix

			# Now override the prefix so that it's the base of the virtual environment
			sys.prefix = str (base_dir)

			vprint ("Active")
			break

		elif venv_ascend == 0:
			vprint ("Ran out of ascensions before finding a virtual environment")
			break

		elif base_dir == base_dir.parent:
			vprint ("Reached the top-level directory before finding a virtual environment")
			break

		else:
			# Scratch one off
			venv_ascend -= 1
			# Ascend
			base_dir = base_dir.parent
			vprint (f"Ascending to {base_dir}")

__virtualenv ()
del __virtualenv

# ==============================================================================

import asyncio
import json
import os.path
import re
import sys
import time

import aiofiles
import aiohttp
from bs4 import BeautifulSoup
from icecream import ic
from playwright.async_api import async_playwright, BrowserContext, BrowserType
from playwright_stealth import stealth_async
import yaml

# ==============================================================================

def yaml_load (path:str) -> dict:
	with open (path, "r", encoding = "utf-8") as file:
		data = yaml.load (file, Loader = yaml.loader.SafeLoader)
		return data

# ==============================================================================

async def twitter_login (context:BrowserContext, username:str, password:str) -> bool:
	try:
		page = await context.new_page ()
		await stealth_async (page)

		await page.goto ("https://twitter.com/i/flow/login")

		field_locator = page.locator ('input')
		username_field = field_locator.first
		await username_field.fill (username)

		button_locator = page.locator ('span', has_text = "Next")
		next_button = button_locator.first
		await next_button.click ()

		field_locator = page.locator ('input')
		password_field = field_locator.last
		await password_field.fill (password)

		button_locator = page.locator ('span', has_text = "Log in")
		login_button = button_locator.first
		await login_button.click ()

		await page.wait_for_url ("**/home")

		if page.url.endswith ("/home"):
			await page.close ()
			return True

	except:
		pass

	await page.close ()
	return False

async def twitter_is_logged_in (context:BrowserContext) -> bool:
	try:
		page = await context.new_page ()
		await stealth_async (page)

		await page.goto ("https://twitter.com")
		await page.wait_for_url ("**/home", timeout = 3000)
		if page.url.endswith ("/home"):
			await page.close ()
			return True
		else:
			await page.close ()
			return False

	except:
		pass

	await page.close ()
	return False

async def twitter_parse_tweet (element) -> dict:
	# Here thar be dragons!

	tweet = {
		"id": None,
		"timestamp": None,
		"author": {
			"username": None,
			"name": None,
			"avatar": None,
		},
		"flags": {
			"is_repost": False,
			"is_pinned": False,
			"has_image": False,
			"has_video": False,
		},
		"content": {
			"text": "",
			"richtext": [],
			"media": [],
		},
	}

	# Check for repost
	locator = element.locator ("div > div > div:nth-of-type(1) a > span")
	if await locator.count () > 0:
		text = await locator.first.inner_text ()
		if re.search (r"\s+reposted$", text) is not None:
			tweet ["flags"]["is_repost"] = True

	# Check for pinned
	locator = element.locator ("div > div > div:nth-of-type(1) div > span")
	if await locator.count () > 0:
		text = await locator.first.inner_text ()
		if text == "Pinned":
			tweet ["flags"]["is_pinned"] = True

	# Author avatar
	#locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(1) > div > div > div > div > div > div > div > div > a > div > div > div > div > img")
	#locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(1) a > div > div > div > div > img")
	locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(1) img")
	if await locator.count () > 0:
		tweet ["author"]["avatar"] = await locator.first.get_attribute ("src")

	# Author name
	locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(2) > div > div > div > div > div > div:nth-of-type(1) > div > a > div > div > span > span")
	#locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(1) div > span > span")
	if await locator.count () > 0:
		tweet ["author"]["name"] = await locator.first.inner_text ()

	# Author username
	locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(2) > div > div > div > div > div > div:nth-of-type(2) > div > div > a > div > span")
	#locator = element.locator ("")
	if await locator.count () > 0:
		text = await locator.first.inner_text ()
		tweet ["author"]["username"] = re.sub (r"^@", "", text)

	# ID
	locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(2) > div > div > div > div > div > div:nth-of-type(2) > div > div a > time")
	#locator = element.locator ("")
	if await locator.count () > 0:
		text = await locator.evaluate ("node => node.parentElement.getAttribute('href')")
		tweet ["id"] = text

	# Timestamp
	locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(2) > div > div > div > div > div > div:nth-of-type(2) > div > div a > time")
	#locator = element.locator ("")
	if await locator.count () > 0:
		text = await locator.first.get_attribute ("datetime")
		tweet ["timestamp"] = text

	# Content text and richtext
	locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(2) > div > *")
	#locator = element.locator ("")
	content_elements = await locator.all ()
	for content_element in content_elements:
		locator = content_element.locator ("a")

		try:
			image_alt = await content_element.get_attribute ("alt", timeout = 10)
		except:
			image_alt = None

		if await locator.count () != 0:
			anchors = await locator.all ()
			for anchor in anchors:
				text = await anchor.inner_text ()
				url = await anchor.get_attribute ("href")

				# Resolve relative and other URL forms
				if url.startswith ("//"):
					url = f"https:{url}"
				elif url.startswith ("/"):
					url = f"https://twitter.com{url}"
				elif url.startswith ("http://") or url.startswith ("https://"):
					pass
				else:
					url = f"https://twitter.com/{url}"

				tweet ["content"]["text"] += text
				tweet ["content"]["richtext"].append ({
					"url": url,
					"text": text,
				})

		elif image_alt is not None:
			tweet ["content"]["text"] += image_alt
			tweet ["content"]["richtext"].append ({
				"url": None,
				"text": image_alt
			})

		else:
			tweet ["content"]["text"] += await content_element.inner_text ()
			tweet ["content"]["richtext"].append ({
				"url": None,
				"text": await content_element.inner_text ()
			})

	# Content media
	locator = element.locator ("div > div > div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(3) > div > div > div > div > div > div a > div > div > img, div > div > div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(3) > div > div > div > div > div > div > a > div > div div > img, div > div > div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(3) div > video")
	#locator = element.locator ("")
	medias = await locator.all ()
	for media in medias:
		src = await media.get_attribute ("src");

		try:
			poster = await media.get_attribute ("poster", timeout = 100);
		except:
			poster = None

		if poster is None:
			tweet ["flags"]["has_image"] = True
			tweet ["content"]["media"].append ({
				"type": "image",
				"image": src,
			})

		else:
			tweet ["flags"]["has_video"] = True
			tweet ["content"]["media"].append ({
				"type": "video",
				"video": src,
				"image": poster,
			})

	return tweet

async def twitter_get_user_tweets (context:BrowserContext, username:str, minimum:int = 10) -> list[dict]:
	tweets = []

	page = await context.new_page ()
	await stealth_async (page)

	await page.goto (f"https://twitter.com/{username}")

	while True:
		await asyncio.sleep (3)

		previous_tweets_length = len (tweets)

		tweet_locator = page.locator ("section > h1 + div > div > div > div > div > article")
		tweet_elements = await tweet_locator.all ()

		for tweet_element in tweet_elements:
			tweets.append (await twitter_parse_tweet (tweet_element))

		tweets = {tweet ["id"]: tweet for tweet in tweets}
		tweets = list (tweets.values ())

		if len (tweets) >= minimum:
			# We have enough posts now
			break

		if len (tweets) == previous_tweets_length:
			# No new posts?
			break

		await page.evaluate ("window.scrollTo (0, document.body.scrollHeight);")

	await page.close ()
	return tweets

# ==============================================================================

async def tweet_to_discord_embed (tweet:dict, config:dict) -> dict:
	embed = {
		"username": config ["discord"]["embed"]["username"],
		"avatar_url": config ["discord"]["embed"]["avatar_url"],
		"attachments": [],
		"flags": config ["discord"]["embed"]["flags"],
		"content": None,
		"embeds": [
			{
				"title": "View on X",
				"description": "",
				"url": f"https://twitter.com{tweet['id']}",
				"color": config ["discord"]["embed"]["color"],
				"fields": [],
				"author": {
					"name": tweet ["author"]["name"],
					"url": f"https://twitter.com/{tweet ['author']['username']}",
					"icon_url": tweet ["author"]["avatar"],
				},
				"footer": {
					"text": f"@{tweet ['author']['username']}",
				},
				"timestamp": tweet ["timestamp"],
			}
		]
	}

	for part in tweet ["content"]["richtext"]:
		text = re.sub (r"([`_*~()\[\]])", r"\\\1", part ["text"])
		text = re.sub (r"^(\s*)([>-])", r"\1\\\2", text)
		text = re.sub (r"^(\s*)(#{1,6})\s+", r"\1\\\2", text)

		if part ["url"] is not None:
			embed ["embeds"][0]["description"] += f"[{text}]({part ['url']})"
		else:
			embed ["embeds"][0]["description"] += text

	needs_video_notice = False
	for item in tweet ["content"]["media"]:
		if item ["type"] == "image":
			embed ["embeds"].append ({
				"url": f"https://twitter.com{tweet['id']}",
				"image": {
					"url": re.sub (r"&name=small\b", "", item ["image"])
				}
			})

		elif item ["type"] == "video":
			url = None # await vxtwitter_get_video_url (tweet ["id"])
			if url is not None:
				embed ["embeds"][0]["video"] = {
					"url": url
				}
			else:
				needs_video_notice = True
				embed ["embeds"].append ({
					"url": f"https://twitter.com{tweet['id']}",
					"image": {
						"url": re.sub (r"&name=small\b", "", item ["image"])
					}
				})

	if needs_video_notice is True:
		embed ["embeds"][0]["fields"].append ({
			"name": "Note",
			"value": "Post contains a video. To view it, click \"View on X\" above.",
			"inline": False
		})

	return embed

async def discord_send_webhook (url:str, embed:dict) -> bool:
	async with aiohttp.ClientSession () as session:
		async with session.post (url, json = embed) as response:
			return await response.text ()

# ==============================================================================

async def vxtwitter_get_video_url (id:str) -> str:
	response = None

	async with aiohttp.ClientSession () as session:
		response = await session.get (
			f"https://vxtwitter.com{id}",
			headers = {
				"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
			}
		)
		response = await response.text ()

	page = BeautifulSoup (response, "html5lib")
	elements = page.css.select ('head meta[property="og:video"]')
	if len (elements) == 0:
		return None

	if "content" not in elements [0].attrs:
		return None

	return elements [0]["content"]

# ==============================================================================

HISTORY_LOCK = asyncio.Lock ()

async def history_has (webhook:str, username:str = None, id:str = None, mode:str = None) -> bool:
	if mode is None:
		mode = "by-author"
	elif mode.lower () not in ("by-account", "by-author"):
		raise ValueError (f"Invalid history mode: {mode}")
	else:
		mode = mode.lower ()

	if id is not None:
		id = re.sub (r"^/([^/]+)/status/(\d+)$", r"\1/\2", id)

	async with HISTORY_LOCK:
		async with aiofiles.open ("history.json", mode = "r") as fh:
			contents = await fh.read ()
		history = json.loads (contents)

		if webhook not in history:
			return False

		if mode == "by-account":
			if username is not None and username.lower () not in history [webhook]:
				return False

			if username is not None and id is not None and id.lower () not in history [webhook][username.lower ()]:
				return False

			return True

		elif mode == "by-author":
			if id is None:
				return True

			for user in history [webhook].keys ():
				if id.lower () in history [webhook][user]:
					return True

			return False

async def history_add (webhook:str, username:str = None, id:str = None, mode:str = None):
	if mode is None:
		mode = "by-author"
	elif mode.lower () not in ("by-account", "by-author"):
		raise ValueError (f"Invalid history mode: {mode}")
	else:
		mode = mode.lower ()

	if id is not None:
		id = re.sub (r"^/([^/]+)/status/(\d+)$", r"\1/\2", id)

	async with HISTORY_LOCK:
		async with aiofiles.open ("history.json", mode = "r") as fh:
			contents = await fh.read ()
		history = json.loads (contents)

		#if mode == "by-account":
		if webhook not in history:
			history [webhook] = {}

		if username is not None and username.lower () not in history [webhook]:
			history [webhook][username.lower ()] = []

		if username is not None and id is not None and id.lower () not in history [webhook][username.lower ()]:
			history [webhook][username.lower ()].append (id.lower ())

		#elif mode == "by-author":
		#	if webhook not in history:
		#		history [webhook] = []
		#
		#	if id is not None and id.lower () not in history [webhook]:
		#		history [webhook].append (id.lower ())

		contents = json.dumps (history, separators = (",", ":"))
		async with aiofiles.open ("history.json", mode = "w") as fh:
			await fh.write (contents)

# ==============================================================================

def add_accounts_last_time (config:dict):
	# Loop through the watch groups
	for watch_index in range (0, len (config ["watches"])):
		# Loop through the watched accounts in the group
		for username in config ["watches"][watch_index]["accounts"].keys ():
			# Add a place to store the last checked timestamp
			config ["watches"][watch_index]["accounts"][username]["last"] = 0

def accounts_ready_to_check (config:dict) -> list[tuple]:
	# A place to store the webhooks and usernames of the accounts that need
	# checking
	to_check = []

	# Loop through the watch groups
	for watch_index in range (0, len (config ["watches"])):
		# Loop through the watched accounts and note the ones that are due for
		# checking
		for username, settings in config ["watches"][watch_index]["accounts"].items ():
			# Compare the last check time to the current time
			if settings ["last"] + settings ["interval"] <= time.time ():
				# It's ready for checking, so append to the list
				to_check.append ((
					watch_index, # config ["watches"][watch_index]["webhook"],
					username,
				))
				# Update the last check time now so it's actually an interval
				# and not a delay between checks
				config ["watches"][watch_index]["accounts"][username]["last"] = time.time ()

	return to_check

def tweet_sendable (settings:dict, tweet:dict) -> bool:
	# Check that the tweet is a type (post, repost, pin) we want to send
	if settings ["posts"] is False and tweet ["flags"]["is_repost"] is False:
		return False
	if settings ["reposts"] is False and tweet ["flags"]["is_repost"] is True:
		return False
	if settings ["pinned"] is False and tweet ["flags"]["is_pinned"] is True:
		return False

	# Check for media constraints
	if (
		(
			settings ["with-images"] is True and
			tweet ["flags"]["has_image"] is True
		) or
		(
			settings ["with-videos"] is True and
			tweet ["flags"]["has_video"] is True
		) or
		(
			settings ["without-media"] is True and
			tweet ["flags"]["has_image"] is False and
			tweet ["flags"]["has_video"] is False
		)
	):
		return True
	else:
		return False

# ==============================================================================

async def main ():
	# Load configuration
	config = yaml_load ("config.yaml")

	# Add an entry to each watched username to track the last time it was
	# checked
	add_accounts_last_time (config)

	# Into the land of the browser
	async with async_playwright () as playwright:
		# Start browser
		browser = await playwright.webkit.launch (headless = True)

		# If no previous browser context state, create one
		if not os.path.isfile ("state.json"):
			# Create a new context
			context = await browser.new_context (
				# Viewport information isn't strictly needed here, but for the
				# sake of uniformity it's included
				viewport = {
					"width": config ["playwright"]["viewport"]["width"],
					"height": config ["playwright"]["viewport"]["height"],
				},
			)
			# Save the context state
			await context.storage_state (path = "state.json")
			# Close the context... we'll re-open using the saved state below
			await context.close ()

		# Open a browser context using the previously saved state so we don't
		# always have to log into Twitter
		context = await browser.new_context (
			# Our previously saved state
			storage_state = "state.json",
			# Viewport size dictates how many tweets are loaded... mainly the
			# height, but width does play a role at smaller dimensions
			viewport = {
				"width": config ["playwright"]["viewport"]["width"],
				"height": config ["playwright"]["viewport"]["height"],
			},
		)

		# Here we go...
		while True:
			# Grab a list of webhooks+accounts ready to be checked
			to_check = accounts_ready_to_check (config)

			# If we don't have any accounts to check we're going to sleep for a
			# short while before checking again
			if len (to_check) == 0:
				# Async sleepy time
				await asyncio.sleep (config ["twitter"]["delays"]["no_check"])
				# Restart the loop
				continue

			# We have accounts to check, so first verify we're still logged in
			if await twitter_is_logged_in (context) is False:
				# We're not logged in... we'll try logging in
				if await twitter_login (
					context,
					config ["twitter"]["login"]["username"],
					config ["twitter"]["login"]["password"]
				) is False:
					# Login failed! Complain to the console
					print ("Error: Failed to log into Twitter!", file = sys.stderr)
					# Async sleepy time so we don't spin hard on trying to login
					await asyncio.sleep (config ["twitter"]["delays"]["failed_login"])
					# Restart the loop
					continue
				else:
					# We're logged in, so save state so we save the cookies
					await context.storage_state (path = "state.json")

			for watch_index, username in to_check:
				# Save us a bunch of typing by setting some variables to long
				# structure paths
				webhook = config ["watches"][watch_index]["webhook"]
				history_mode = config ["watches"][watch_index]["history"]
				settings = config ["watches"][watch_index]["accounts"][username]

				# Check for a history entry (not necessarily history) for this
				# username under this webhook
				if await history_has (webhook, username, mode = "by-account") is False:
					# No history entry? It's new! Grab a BUNCH of posts because
					# sometimes ordering changes to bring old posts to the top
					tweets = await twitter_get_user_tweets (context, username, minimum = config ["twitter"]["history_length"])
					# Time to "check" the tweets
					for tweet in tweets:
						# Add to history because we're building out a new
						# history
						await history_add (webhook, username, tweet ["id"], mode = history_mode)

				else:
					# Just a normal check... Load the user's tweets
					tweets = await twitter_get_user_tweets (context, username, minimum = config ["twitter"]["check_length"])

					# Time to check the tweets
					for tweet in tweets:
						# Don't send a tweet if we've already sent it
						if await history_has (webhook, username, tweet ["id"], mode = history_mode) is True:
							# Next tweet please
							continue

						# Is this something we're supposed to send to the webhook?
						if tweet_sendable (settings, tweet) is True:
							# Generate the Discord embed object for the tweet
							embed = await tweet_to_discord_embed (tweet, config)
							# Deliver the embed object to the webhook
							await discord_send_webhook (webhook, embed)

						# Add to history regardless of whether or not we
						# send it
						await history_add (webhook, username, tweet ["id"], mode = history_mode)

		# We probably won't get here, but we'll handle closing of the browser in
		# case we somehow do
		await browser.close ()

# ==============================================================================

if __name__ == "__main__":
	import asyncio
	import inspect
	try:
		if inspect.iscoroutinefunction (main):
			asyncio.run (main ())
		else:
			main ()
	except KeyboardError:
		pass
