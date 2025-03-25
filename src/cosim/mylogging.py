import logging 
import sys

from pathlib import Path
    
def getLogger(logger_name: str, path_to_file: str, level=logging.INFO,
              formatter=logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")):
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    
    # Ensure the parent directories exist
    Path(path_to_file).parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.FileHandler(path_to_file, encoding="utf-8", mode="w+")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger