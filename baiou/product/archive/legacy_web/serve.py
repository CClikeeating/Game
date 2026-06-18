from __future__ import annotations

from .app import create_app, load_web_config


def main() -> None:
    config = load_web_config()
    create_app(config).run(host=config["host"], port=config["port"], debug=config["debug"], use_reloader=False)


if __name__ == "__main__":
    main()


