from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.fields import EmailField
from wtforms.validators import Email, InputRequired


class AddHubForm(FlaskForm):
    name = StringField("Название", validators=[InputRequired(message="Обязательное поле.")])
    email = EmailField("Email", validators=[InputRequired(message="Обязательное поле."), Email()])
    submit = SubmitField("Добавить")


class SelectHubForm(FlaskForm):
    hub_id = SelectField("Выбор хаба", validators=[InputRequired(message="Обязательное поле.")], coerce=int)
    submit = SubmitField("Сохранить")
