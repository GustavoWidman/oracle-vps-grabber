from utils.oracle import OracleInstancePrep
from time import sleep
import requests
import os


def main():
	instance = OracleInstancePrep()

	def try_create(counter = 0):
		try:
			response = instance.create_instance()
			return send_to_discord(True, response)
		except Exception as e:
			if e.status == 500 and e.message == 'Out of host capacity.':
				print("Retrying in 30 seconds...")
				sleep(30)
				return try_create()
			elif e.status == 429 and e.message == 'Too many requests for the user':
				counter += 1
				print(f"Ratelimited, retrying in {30*counter} seconds...")
				sleep(30*counter)
				return try_create(counter)
			else:
				print(e)
				return send_to_discord(False, e)

	try_create()


def send_to_discord(success, response):
	url = os.getenv("DISCORD_WEBHOOK")
	user_id = os.getenv("DISCORD_USER_ID")
	ping = f"<@{user_id}>\n" if user_id else ""

	if not url: return

	data = {
		"content": f"{ping}Success: {success}\nResponse: {response}"
	}
	requests.post(url, json=data)

main()