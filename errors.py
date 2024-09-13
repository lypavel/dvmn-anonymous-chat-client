class InvalidTokenError(Exception):
    def __init__(self, token: str, message=None) -> None:
        super().__init__(message)
        self.token = token

    def __str__(self):
        return (f'Invalid token: {self.token}.\n\n'
                'Check your credentials or create new user '
                'by running `register.py`')
