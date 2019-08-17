import logging

def log_config():
    # create logger
    logger = logging.getLogger(__package__)
    logger.setLevel(logging.DEBUG)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter(
        '%(asctime)s|%(levelname)5s|%(name)s.%(filename)s.%(module)s.%(funcName)s:%(lineno)4d | %(message)s'
    )
    # add formatter to ch
    ch.setFormatter(formatter)
    # add ch to logger
    logger.addHandler(ch)