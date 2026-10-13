class WorkStopped(Exception):
    def __init__(self, status):
        self.status = status


class ModelLimit(Exception):
    def __init__(self, code):
        self.code = code
