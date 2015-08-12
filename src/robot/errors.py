class RobotError(Exception):
    """Base class for Robot Framework errors.
    Do not raise this method but use more specific errors instead.
    """

    def __init__(self, message='', details=''):
        Exception.__init__(self, message)
        self.details = details

    @property
    def message(self):
        return self.__unicode__()


class DataError(RobotError):
    """Used when the provided test data is invalid.
    DataErrors are not caught by keywords that run other keywords
    (e.g. `Run Keyword And Expect Error`).
    """
