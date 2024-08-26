from authlib.integrations.flask_client.apps import FlaskOAuth2App


class YandexOauth2Config(FlaskOAuth2App):
    NAME = "yandex"
    OAUTH_APP_CONFIG = {
        "api_base_url": "https://login.yandex.ru/",
        "access_token_url": "https://oauth.yandex.ru/token",
        "authorize_url": "https://oauth.yandex.ru/authorize",
        "userinfo_endpoint": "info",
    }

    @staticmethod
    def map_profile(user_info: dict) -> dict:
        if not user_info.get("is_avatar_empty", True) and user_info.get("default_avatar_id"):
            tpl = "https://avatars.yandex.net/get-yapic/{}/islands-200"
            picture = tpl.format(user_info["default_avatar_id"])
        else:
            picture = None
        user_info["email"] = user_info.get("default_email")
        user_info["name"] = user_info.get("real_name")
        user_info["picture"] = picture
        user_info["phone_number"] = user_info.get("default_phone", {}).get("number")
        user_info["gender"] = user_info.get("sex")
        return user_info
