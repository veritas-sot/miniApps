import abc

class Dispatcher(abc.ABC):

    @abc.abstractmethod
    def __init__(self, config):
        pass

    @abc.abstractmethod
    def set_args(self, parser):
        pass

    @abc.abstractmethod
    def start(self, args):
        pass
