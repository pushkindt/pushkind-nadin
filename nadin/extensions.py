from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy

login_manager = LoginManager()
migrate = Migrate(render_as_batch=True)
db = SQLAlchemy()
moment = Moment()
mail = Mail()
