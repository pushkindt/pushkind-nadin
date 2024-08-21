from authlib.integrations.flask_client.apps import FlaskOAuth2App


class YandexOauth2Config(FlaskOAuth2App):
    NAME = "yandex"
    OAUTH_APP_CONFIG = {
        "api_base_url": "https://login.yandex.ru/",
        "access_token_url": "https://oauth.yandex.com/token",
        "authorize_url": "https://oauth.yandex.com/authorize",
        "userinfo_endpoint": "info",
    }

    @staticmethod
    def map_profile(user_info: dict) -> dict:
        if not user_info.get("is_avatar_empty", True) and user_info.get("default_avatar_id"):
            tpl = "https://avatars.yandex.net/get-yapic/{}/islands-200"
            picture = tpl.format(user_info["default_avatar_id"])
        else:
            picture = None
        return {
            "email": user_info.get("default_email"),
            "name": user_info.get("display_name"),
            "picture": picture,
        }
