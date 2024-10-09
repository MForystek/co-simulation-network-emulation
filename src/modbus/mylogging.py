import logging 
    
def getLogger(logger_name: str, file_name: str, level=logging.INFO):
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(file_name, encoding="utf-8", mode="w")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger