import sys

class Logger:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"

    @classmethod
    def banner(cls, text: str):
        print(f"\n{cls.BOLD}{cls.CYAN}════════════════════════════════════════════════════════════{cls.RESET}")
        print(f" {cls.BOLD}{cls.CYAN}{text}{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}════════════════════════════════════════════════════════════{cls.RESET}\n")

    @classmethod
    def step(cls, step_str: str, msg: str):
        print(f"{cls.BOLD}{cls.BLUE}[{step_str}]{cls.RESET} {msg}")

    @classmethod
    def success(cls, msg: str):
        print(f"{cls.GREEN}✔ {msg}{cls.RESET}")

    @classmethod
    def info(cls, msg: str):
        print(f"{cls.CYAN}ℹ {msg}{cls.RESET}")

    @classmethod
    def warn(cls, msg: str):
        print(f"{cls.YELLOW}⚠ {msg}{cls.RESET}")

    @classmethod
    def error(cls, msg: str):
        print(f"{cls.RED}✖ {msg}{cls.RESET}", file=sys.stderr)

    @classmethod
    def log(cls, msg: str):
        print(f"  {cls.GRAY}{msg}{cls.RESET}")
