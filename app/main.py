import sys
from app.bootstrap import ApplicationBootstrap


def main() -> int:
    bootstrap = ApplicationBootstrap()
    return bootstrap.run()


if __name__ == "__main__":
    sys.exit(main())