from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import LoginRequired
import logging

logger = logging.getLogger()
SESSION_FILE_NAME = 'session.json'
USERNAME = 'danniel_ksong'
PASSWORD = 'Mario@123*'

def login_user():
    """
    Attempts to login to Instagram using either the provided session information
    or the provided username and password.
    """

    cl = Client()
    session = None

    if Path(SESSION_FILE_NAME).exists():
        session = cl.load_settings(Path(SESSION_FILE_NAME))

    login_via_session = False
    login_via_pw = False

    if session:
        print('Logging in to Instagram via session...')
        login_via_session = True
        try:
            cl.set_settings(session)
            cl.login(USERNAME, PASSWORD)

            # check if session is valid
            try:
                cl.get_timeline_feed()
            except LoginRequired:
                logger.error("Session is invalid, need to login via username and password")

                old_session = cl.get_settings()

                # use the same device uuids across logins
                cl.set_settings({})
                cl.set_uuids(old_session["uuids"])

                cl.login(USERNAME, PASSWORD)
            login_via_session = True
        except Exception as e:
            logger.error("Couldn't login user using session information: %s" % e)

    if not login_via_session:
        try:
            before_ip = cl._send_public_request("https://api.ipify.org/")
            print(before_ip)
            logger.error("Attempting to login via username and password. username: %s" % USERNAME)
            if cl.login(USERNAME, PASSWORD):
                login_via_pw = True
        except Exception as e:
            logger.error("Couldn't login user using username and password: %s" % e)

    if not login_via_pw and not login_via_session:
        raise Exception("Couldn't login user with either password or session")

if __name__ == '__main__':
    login_user()
