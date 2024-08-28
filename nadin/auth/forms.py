from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.fields import EmailField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from nadin.models.order import User


class LoginForm(FlaskForm):
    email = EmailField(
        "Электронная почта",
        validators=[
            DataRequired(message="Электронная почта - обязательное поле."),
            Email(message="Некорректный адрес электронной почты."),
        ],
    )
    password = PasswordField("Пароль", validators=[DataRequired(message="Пароль - обязательное поле.")])
    remember_me = BooleanField("Запомнить меня")
    submit = SubmitField("Авторизация")


class RegistrationForm(FlaskForm):
    email = EmailField(
        "Электронная почта",
        validators=[
            DataRequired(message="Электронная почта - обязательное поле."),
            Email(message="Некорректный адрес электронной почты."),
            Length(max=128, message="Слишком длинный электронный адрес."),
        ],
    )
    password = PasswordField("Пароль", validators=[DataRequired(message="Пароль - обязательное поле.")])
    password2 = PasswordField(
        "Повторите пароль", validators=[DataRequired(), EqualTo("password", message="Пароли не совпадают.")]
    )
    submit = SubmitField("Регистрация")

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.lower()).first()
        if user is not None:
            raise ValidationError("Этот адрес электронной почты уже занят.")


class ResetPasswordRequestForm(FlaskForm):
    email = StringField(
        "Электронная почта",
        validators=[
            DataRequired(message="Электронная почта - обязательное поле."),
            Email(message="Некорректный адрес электронной почты."),
        ],
    )
    submit = SubmitField("Сбросить")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("Пароль", validators=[DataRequired(message="Пароль - обязательное поле.")])
    password2 = PasswordField(
        "Повторите пароль", validators=[DataRequired(), EqualTo("password", message="Пароли не совпадают.")]
    )
    submit = SubmitField("Сменить")
