import argparse
import logging

import httpx
import uvicorn

from history import daemon
from history.config import load_config
from history.server.app import create_app


LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def main() -> None:
    parser = argparse.ArgumentParser(prog="hist")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("server", help="run the API server")
    run = commands.add_parser("daemon", help="pull from every source on a schedule")
    run.add_argument("--once", action="store_true", help="sync everything once, then exit")
    commands.add_parser("status", help="show what the server has")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()

    if args.command == "server":
        if config.host not in LOOPBACK_HOSTS and not config.api_token:
            parser.error(f"set api_token in the config before binding to {config.host}")
        app = create_app(config.db_path, config.api_token)
        uvicorn.run(app, host=config.host, port=config.port)
    elif args.command == "daemon" and args.once:
        daemon.run_once(config)
    elif args.command == "daemon":
        daemon.run_forever(config)
    elif args.command == "status":
        response = httpx.get(f"{config.server_url}/stats", headers=config.auth_headers)
        rows = response.raise_for_status().json()
        for row in rows:
            print(f"{row['source']:<14}{row['events']:>9} events {row['fixes']:>7} fixes")
