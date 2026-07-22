import os

from dotenv import load_dotenv


load_dotenv()


class BaseConfig:
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///tss_untisanmeldung.sqlite")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH"))


class DevConfig(BaseConfig):
    DEBUG = True
