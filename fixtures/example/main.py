from auth import authenticate
from database import get_user


def login(username, password):
    user = get_user(username)
    if user:
        return authenticate(user, password)
    return False


def main():
    return login("admin", "1234")


if __name__ == "__main__":
    main()
