from pathlib import Path
import sys

from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent / "src"))

load_dotenv()

from umamusume_web_crawler.cli import main


if __name__ == "__main__":
    main()
