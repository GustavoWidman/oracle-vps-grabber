from oci.exceptions import RequestException
from utils.oracle import OracleInstancePrep
from time import sleep
import requests
import os


def main():
	instance = OracleInstancePrep()

	counter = 0
	while True:
		try:
			response = instance.create_instance()
			return send_to_discord(True, response)
		except RequestException as e:
			counter += 1
			print(f"Retrying in {60*counter} seconds...")
			sleep(60*counter)
		except Exception as e:
			if e.status == 500:
				print("Retrying in 30 seconds...")
				sleep(30)
				counter = 0
			elif e.status == 429:
				counter += 1
				print(f"Ratelimited, retrying in {30*counter} seconds...")
				sleep(30*counter)
			elif e.status == 502:
				send_to_discord(False, e)
				print("Internal error, retrying in 60 seconds...")
				sleep(60)
				counter = 0
			else:
				print(e)
				return send_to_discord(False, e)


def send_to_discord(success, response, continued = False):
	url = os.getenv("DISCORD_WEBHOOK")
	user_id = os.getenv("DISCORD_USER_ID")
	ping = f"<@{user_id}>\n" if user_id else ""
	continue_message = "This error was ignored and we will be continuing as normal." if continued else ""

	if not url: return

	data = {
		"content": f"{ping}Success: {success}\nResponse: {response}\n{continue_message}"
	}
	requests.post(url, json=data)

main()