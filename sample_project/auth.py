import hashlib
import os

class AuthService:
    def __init__(self):
        self.secret = os.getenv("SECRET_KEY", "default_secret")

    def hash_password(self, password):
        return hashlib.sha256((password + self.secret).encode()).hexdigest()

    def verify_password(self, password, hashed):
        return self.hash_password(password) == hashed

def login_user(username, password):
    pass
