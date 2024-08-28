from flask_wtf import FlaskForm
from pydantic import ValidationError
from wtforms import SelectField, StringField, TextAreaField
from wtforms.fields import EmailField
from wtforms.validators import DataRequired, Email, InputRequired, Length

from nadin.models.project import ProjectPriceLevel
from nadin.models.shopping_cart import ApiShoppingCartModel


class ShoppingCartField(StringField):
    def _value(self):
        return self.data.model_dump_json() if self.data else ""

    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = ApiShoppingCartModel.model_validate_json(valuelist[0])
            except ValidationError as exc:
                raise ValueError("Некорректное поле данных (корзина).") from exc
        else:
            self.data = None

    def pre_validate(self, form):
        super().pre_validate(form)
        if self.data:
            try:
                self.data.model_dump_json()
            except TypeError as exc:
                raise TypeError("Не корректное поле данных (корзина).") from exc


class OrderForm(FlaskForm):
    class Meta:
        csrf = False

    email = EmailField(
        "Электронная почта",
        validators=[
            DataRequired(message="Обязательное поле."),
            Email(message="Некорректный адрес электронной почты."),
        ],
    )
    price_level = SelectField(
        "Уровень цен",
        validators=[InputRequired(message="Некорректный уровень цен.")],
        coerce=int,
        choices=[(int(role), str(role)) for role in ProjectPriceLevel],
    )
    comment = TextAreaField(
        "Комментарий",
        validators=[Length(max=256, message="Слишком длинный комментарий.")],
    )
    cart = ShoppingCartField("Корзина", validators=[DataRequired(message="Обязательное поле.")])
