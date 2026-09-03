try:
    from .wrapper import main
except ImportError:
    from wrapper import main
import sys

if __name__ == "__main__":
    sys.exit(main())
