import sys
import argparse

from spotidal.config import load_config


def main():
    parser = argparse.ArgumentParser(
        description="Sync playlists and favorites between Spotify and Tidal",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--autorun", action="store_true", help="run sync using saved configuration")
    group.add_argument("--setup", action="store_true", help="enter interactive setup wizard")
    group.add_argument("--oneshot", action="store_true", help="interactive one-shot sync (doesn't save sync selections)")
    parser.add_argument("--config", default="config.yml", help="path to config file (default: config.yml)")
    args = parser.parse_args()

    config_path = args.config
    config = load_config(config_path)

    if args.autorun:
        from spotidal.run import run_sync

        if config is None:
            print(f"No config found at '{config_path}'. Run `spotidal` first to set up.")
            sys.exit(1)
        run_sync(config, config_path)
    elif args.oneshot:
        from spotidal.run import run_oneshot

        run_oneshot(config, config_path)
    else:
        from spotidal.setup import run_wizard
        from spotidal.run import run_sync

        config, action = run_wizard(config, config_path)
        if action == "save_and_run":
            run_sync(config, config_path)
        elif action == "cancel":
            print("Setup cancelled.")


if __name__ == "__main__":
    main()
    sys.exit(0)
