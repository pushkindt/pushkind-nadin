from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.fields import EmailField
from wtforms.validators import Email, InputRequired, Length

from nadin.utils import IMAGES


class AddHubForm(FlaskForm):
    name = StringField("Название", validators=[InputRequired(message="Обязательное поле.")])
    email = EmailField("Email", validators=[InputRequired(message="Обязательное поле."), Email()])
    submit = SubmitField("Добавить")


class SelectHubForm(FlaskForm):
    hub_id = SelectField("Выбор хаба", validators=[InputRequired(message="Обязательное поле.")], coerce=int)
    submit = SubmitField("Выбрать хаб")


class AppSettingsForm(FlaskForm):
    email = EmailField(
        "Электронная почта 1С",
        validators=[Length(max=128, message="Слишком длинное название.")],
    )
    enable = BooleanField("Включить рассылку 1С")
    order_id_bias = IntegerField("Константа номеров заявок")
    image = FileField(
        label="Логотип",
        validators=[FileAllowed(IMAGES, "Разрешены только изображения.")],
    )
    single_category_orders = BooleanField("Заявки с одной категорией")
    alert = TextAreaField("Предупреждение")
    store_url = StringField("URL магазина")
    contacts = TextAreaField(
        "Контакты", description='Контакты в формате <a href="https://www.markdownguide.org/basic-syntax/">markdown</a>'
    )
    submit = SubmitField("Сохранить")
