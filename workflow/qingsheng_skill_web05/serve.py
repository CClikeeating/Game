from __future__ import annotations

from .app import create_app


def main() -> None:
    create_app().run(host="127.0.0.1", port=7860, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
