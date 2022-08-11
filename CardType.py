from enum import Enum

class CardType(Enum):
        INVALID_CARD = -1
        SHUTDOWN_CARD = 1
        PROXY_CARD = 2
        TRAINING_CARD = 3
        USER_CARD = 4
