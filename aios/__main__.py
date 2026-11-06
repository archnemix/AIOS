"""Run the gateway or inspect CPU availability."""

import argparse

from .config import Config
from .gateway import GatewayServer
from .hardware import recommended_threads


def main():
    parser = argparse.ArgumentParser(description="AIOS CPU inference gateway")
    parser.add_argument("command", choices=("serve", "hardware"))
    args = parser.parse_args()
    if args.command == "hardware":
        print(f"Available logical CPUs: {recommended_threads()}")
        print("Benchmark several thread counts; more threads are not always faster.")
        return
    try:
        config = Config.from_env()
        server = GatewayServer((config.host, config.port), config)
    except (ValueError, OSError) as error:
        parser.exit(1, f"AIOS: {error}\n")
    print(f"AIOS gateway listening on http://{config.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
