def test_dynaconf_is_on_testing_env(app):
    assert app.config["title"] == "testing"
    assert app.config.current_env == "testing"
