import json
from datetime import datetime, timezone

from flask_login import current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    DecimalField,
    FieldList,
    Form,
    FormField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields import DateField, EmailField, URLField
from wtforms.validators import DataRequired, Email, InputRequired, Length, Optional, ValidationError

from nadin.extensions import db
from nadin.main.utils import SendEmailNotification
from nadin.models import EventType, OrderEvent, OrderLimitsIntervals, ProjectPriceLevel, UserRoles


class JSONField(StringField):
    def _value(self):
        return json.dumps(self.data, ensure_ascii=False) if self.data else ""

    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = json.loads(valuelist[0])
            except ValueError as exc:
                raise ValueError("Не корректное поле данных.") from exc
        else:
            self.data = None

    def pre_validate(self, form):
        super().pre_validate(form)
        if self.data:
            try:
                json.dumps(self.data, ensure_ascii=False)
            except TypeError as exc:
                raise TypeError("Не корректное поле данных.") from exc


################################################################################
# Approve page
################################################################################


class InitiativeForm(FlaskForm):
    project = SelectField(
        "Клиент",
        validators=[DataRequired(message="Название клиента - обязательное поле.")],
        coerce=int,
    )
    categories = SelectMultipleField(
        "Категории",
        validators=[DataRequired(message="Категории заявки - обязательное поле.")],
        coerce=int,
    )
    submit = SubmitField("Сохранить")


class ApproverForm(FlaskForm):
    income_statement = SelectField(
        "Статья БДР",
        validators=[DataRequired(message="Статья БДР - обязательное поле.")],
        coerce=int,
    )
    cashflow_statement = SelectField(
        "Статья БДДС",
        validators=[DataRequired(message="Статья БДДС - обязательное поле.")],
        coerce=int,
    )
    submit = SubmitField("Сохранить")


class LeaveCommentForm(FlaskForm):
    comment = TextAreaField(
        "Комментарий",
        validators=[Length(max=256, message="Слишком длинный комментарий.")],
    )
    notify_reviewers = SelectMultipleField("Уведомить ↓", coerce=int)
    submit = SubmitField("Сохранить")

    def comment_and_send_email(self, order, event_type):
        stripped = self.comment.data.strip() or None
        reviewers = {r.id: r.name for r in order.reviewers}
        event = OrderEvent(
            order_id=order.id,
            user_id=current_user.id,
            type=event_type,
            timestamp=datetime.now(tz=timezone.utc),
            data=stripped,
        )
        db.session.add(event)
        if len(self.notify_reviewers.data) > 0:
            SendEmailNotification("comment", order, self.notify_reviewers.data, data=self.comment.data)
            message = "Уведомление выслано: "
            message += ", ".join(reviewers[r] for r in self.notify_reviewers.data)
            event = OrderEvent(
                user_id=current_user.id,
                order_id=order.id,
                type=EventType.notification,
                data=message,
                timestamp=datetime.now(tz=timezone.utc),
            )
            db.session.add(event)


class OrderApprovalForm(FlaskForm):
    product_id = IntegerField("Идентификатор товара", render_kw={"hidden": ""})
    comment = TextAreaField("Замечание", validators=[Length(max=512, message="Слишком длинное замечание.")])
    submit = SubmitField("Сохранить")


class ChangeQuantityForm(FlaskForm):
    product_id = IntegerField(
        "Идентификатор товара",
        validators=[DataRequired(message="ID товара - обязательное поле.")],
        render_kw={"hidden": ""},
    )
    product_quantity = IntegerField(
        "Количество товара",
        validators=[InputRequired(message="Невозможное значение количества.")],
        render_kw={"type": "number", "step": 1, "min": 0},
    )
    submit = SubmitField("Сохранить")

    def validate_product_quantity(self, product_quantity):
        if product_quantity.data < 0:
            raise ValidationError("Количество не может быть меньше нуля.")


class SplitOrderForm(FlaskForm):
    products = JSONField(
        "products",
        validators=[InputRequired(message="Список позиций не может быть пустым.")],
    )
    submit = SubmitField("Разделить")


################################################################################
# Stores page
################################################################################


class AddStoreForm(FlaskForm):
    name = StringField(
        "Поставщик",
        validators=[
            DataRequired(message="Название поставщика - обязательное поле."),
            Length(max=128, message="Слишком длинное название."),
        ],
    )
    email = EmailField(
        "Электронная почта",
        validators=[
            DataRequired(message="Электронная почта - обязательное поле."),
            Email(),
            Length(max=128, message="Слишком длинный электронный адрес."),
        ],
    )
    password = PasswordField("Пароль", validators=[DataRequired(message="Пароль - обязательное поле.")])
    submit = SubmitField("Создать")


################################################################################
# Settings page
################################################################################


class UserSettings(Form):
    full_name = StringField(
        "Имя",
        validators=[
            DataRequired(message="Имя - обязательное поле."),
            Length(max=128, message="Слишком длинное имя."),
        ],
    )
    phone = StringField("Телефон", validators=[Length(max=128, message="Слишком длинный телефон.")])
    categories = SelectMultipleField("Мои категории ↓", coerce=int)
    projects = SelectMultipleField("Мои клиенты ↓", coerce=int)
    position = StringField(
        "Роль",
        validators=[
            InputRequired(message="Роль - обязательное поле."),
            Length(max=128, message="Слишком длинная роль."),
        ],
    )
    location = StringField("Площадка", validators=[Length(max=512, message="Слишком длинное название.")])
    email_new = BooleanField("Новые заявки")
    email_modified = BooleanField("Заявка изменена")
    email_disapproved = BooleanField("Заявка отклонена")
    email_approved = BooleanField("Заявка согласована")
    email_comment = BooleanField("Комментарий к заявке")


class UserRolesForm(FlaskForm):
    user_id = IntegerField("Идентификатор пользователя", render_kw={"hidden": ""})
    role = SelectField(
        "Права доступа",
        validators=[InputRequired(message="Некорректные права доступа пользователя.")],
        coerce=int,
        choices=[(int(role), str(role)) for role in UserRoles],
    )
    about_user = FormField(UserSettings, [DataRequired()])
    note = TextAreaField("Заметка")
    birthday = DateField("День рождения", validators=[Optional()])
    dashboard_url = URLField("Дашборд", validators=[Length(max=512, message="Слишком длинное URL.")])
    submit = SubmitField("Сохранить")


class UserSettingsForm(FlaskForm):
    about_user = FormField(UserSettings, [DataRequired()])
    submit = SubmitField("Сохранить")


################################################################################
# Index page
################################################################################


class MergeOrdersForm(FlaskForm):
    orders = JSONField(
        "orders",
        validators=[InputRequired(message="Список заявок не может быть пустым.")],
    )
    submit = SubmitField("Объединить")


class SaveOrdersForm(FlaskForm):
    orders = JSONField(
        "orders",
        validators=[InputRequired(message="Список заявок не может быть пустым.")],
    )


################################################################################
# Admin page
################################################################################


class AppSettingsForm(FlaskForm):
    email = EmailField(
        "Электронная почта 1С",
        validators=[Length(max=128, message="Слишком длинное название.")],
    )
    enable = BooleanField("Включить рассылку 1С")
    order_id_bias = IntegerField("Константа номеров заявок")
    image = FileField(
        label="Логотип (png)",
        validators=[FileAllowed(["png"], "Разрешены только изображения PNG!")],
    )
    single_category_orders = BooleanField("Заявки с одной категорией")
    alert = TextAreaField("Предупреждение")
    submit = SubmitField("Сохранить")


class AddProjectForm(FlaskForm):
    project_name = StringField(
        "Название",
        validators=[
            DataRequired(message="Название клиента - обязательное поле."),
            Length(max=128, message="Слишком длинное название."),
        ],
    )
    uid = StringField("Код", validators=[Optional(), Length(max=128, message="Слишком длинный код.")])
    tin = StringField("ИНН", validators=[Optional(), Length(max=128, message="Слишком длинный ИНН.")])
    phone = StringField("Телефон", validators=[Optional(), Length(max=128, message="Слишком длинный телефон.")])
    email = StringField(
        "Электронная почта", validators=[Optional(), Length(max=128, message="Слишком длинная электронная почта.")]
    )
    contact = StringField(
        "Контактное лицо", validators=[Optional(), Length(max=128, message="Слишком длинное имя контактного лица.")]
    )
    legal_address = StringField(
        "Юридический адрес", validators=[Optional(), Length(max=128, message="Слишком длинный юридический адрес.")]
    )
    shipping_address = StringField(
        "Адрес доставки", validators=[Optional(), Length(max=128, message="Слишком длинный адрес доставки.")]
    )
    note = TextAreaField("Заметка")
    price_level = SelectField(
        "Уровень цен",
        validators=[InputRequired(message="Необходимо указать уровень цен.")],
        coerce=int,
        choices=[(int(level), str(level)) for level in ProjectPriceLevel],
    )
    submit = SubmitField("Добавить")


class EditProjectForm(FlaskForm):
    project_id = IntegerField(
        "ID клиента",
        validators=[DataRequired(message="ID клиента - обязательное поле.")],
    )
    project_name = StringField(
        "Название",
        validators=[
            DataRequired(message="Название клиента - обязательное поле."),
            Length(max=128, message="Слишком длинное название."),
        ],
    )
    uid = StringField("Код", validators=[Optional(), Length(max=128, message="Слишком длинный код.")])
    tin = StringField("ИНН", validators=[Optional(), Length(max=128, message="Слишком длинный ИНН.")])
    phone = StringField("Телефон", validators=[Optional(), Length(max=128, message="Слишком длинный телефон.")])
    email = StringField(
        "Электронная почта", validators=[Optional(), Length(max=128, message="Слишком длинная электронная почта.")]
    )
    contact = StringField(
        "Контактное лицо", validators=[Optional(), Length(max=128, message="Слишком длинное имя контактного лица.")]
    )
    legal_address = StringField(
        "Юридический адрес", validators=[Optional(), Length(max=128, message="Слишком длинный юридический адрес.")]
    )
    shipping_address = StringField(
        "Адрес доставки", validators=[Optional(), Length(max=128, message="Слишком длинный адрес доставки.")]
    )
    note = TextAreaField("Заметка")
    enabled = BooleanField("Включить клиент")
    price_level = SelectField(
        "Уровень цен",
        validators=[InputRequired(message="Необходимо указать уровень цен.")],
        coerce=int,
        choices=[(int(level), str(level)) for level in ProjectPriceLevel],
    )
    submit = SubmitField("Изменить")


class UploadProjectsForm(FlaskForm):
    projects = FileField(
        label="Клиенты",
        validators=[
            FileRequired("Разрешены только XLSX."),
            FileAllowed(["xlsx"], "Разрешены только XLSX."),
        ],
    )
    submit = SubmitField("Загрузить")


class AddCategoryForm(FlaskForm):
    category_name = StringField(
        "Название",
        validators=[
            DataRequired(message="Название категории - обязательное поле."),
            Length(max=128, message="Слишком длинное название."),
        ],
    )
    parent = SelectField(
        "Категория-родитель",
        validators=[Optional()],
        coerce=int,
    )
    submit = SubmitField("Создать")


class CategoryResponsibilityForm(FlaskForm):
    category_id = IntegerField(
        "ID категории",
        validators=[DataRequired(message="ID категории - обязательное поле.")],
    )
    responsible = StringField(
        "Ответственный",
        validators=[
            DataRequired(message="Ответственный - обязательное поле."),
            Length(max=128, message="Слишком длинное имя ответственного."),
        ],
    )
    functional_budget = StringField(
        "Функциональный бюджет",
        validators=[
            DataRequired(message="Функциональный бюджет - обязательное поле."),
            Length(max=128, message="Слишком длинное название ФДБ."),
        ],
    )
    income_statement = SelectField(
        "Статья БДР",
        validators=[DataRequired(message="Статья БДР - обязательное поле.")],
        coerce=int,
    )
    cashflow_statement = SelectField(
        "Статья БДДС",
        validators=[DataRequired(message="Статья БДДС - обязательное поле.")],
        coerce=int,
    )
    code = StringField(
        "Код",
        validators=[
            DataRequired(message="Код категории - обязательное поле."),
            Length(max=128, message="Слишком длинный код."),
        ],
    )
    image = FileField(
        label="Изображение",
        validators=[FileAllowed(["jpg", "png"], "Разрешены только изображения JPG и PNG!")],
    )
    submit = SubmitField("Сохранить")


class AddIncomeForm(FlaskForm):
    income_name = StringField(
        "БДР",
        validators=[
            DataRequired(message="БДР - обязательное поле."),
            Length(max=128, message="Слишком длинное название."),
        ],
    )
    submit = SubmitField("Добавить")


class AddCashflowForm(FlaskForm):
    cashflow_name = StringField(
        "БДДС",
        validators=[
            DataRequired(message="БДДС - обязательное поле."),
            Length(max=128, message="Слишком длинное название."),
        ],
    )
    submit = SubmitField("Добавить")


class EditIncomeForm(FlaskForm):
    income_id = IntegerField("ID БДР", [DataRequired(message="ID БДР - обязательное поле.")])
    income_name = StringField(
        "БДР",
        validators=[
            DataRequired(message="БДР - обязательное поле."),
            Length(max=128, message="Слишком длинное название."),
        ],
    )
    submit = SubmitField("Изменить")


class EditCashflowForm(FlaskForm):
    cashflow_id = IntegerField("ID БДДС", validators=[DataRequired(message="ID БДДС - обязательное поле.")])
    cashflow_name = StringField(
        "БДДС",
        validators=[
            DataRequired(message="БДДС - обязательное поле."),
            Length(max=128, message="Слишком длинное название."),
        ],
    )
    submit = SubmitField("Изменить")


################################################################################
# Limits page
################################################################################


class AddLimitForm(FlaskForm):
    interval = SelectField(
        "Интервал",
        validators=[InputRequired(message="Некорректный интервал лимита.")],
        coerce=int,
        choices=[(int(i), str(i)) for i in OrderLimitsIntervals],
    )
    value = DecimalField("Лимит", validators=[DataRequired(message="Лимит - обязательное поле.")])
    project = SelectField(
        "Клиент",
        validators=[DataRequired(message="Клиент - обязательное поле.")],
        coerce=int,
    )
    cashflow = SelectField(
        "БДДС",
        validators=[DataRequired(message="БДДС - обязательное поле.")],
        coerce=int,
    )
    submit = SubmitField("Создать")


################################################################################
# Shop page
################################################################################


class CartItemForm(Form):
    product = IntegerField(
        "Идентификатор товара",
        validators=[DataRequired(message="ID товара - обязательное поле.")],
        render_kw={"hidden": ""},
    )
    quantity = IntegerField(
        "Количество товара",
        validators=[InputRequired(message="Невозможное значение количества.")],
        render_kw={"type": "number", "step": 1, "min": 0},
    )
    text = TextAreaField("Текст")
    options = JSONField("Опции")

    def validate_quantity(self, quantity):
        if quantity.data < 0:
            raise ValidationError("Количество не может быть меньше нуля.")


class CreateOrderForm(FlaskForm):
    project_id = IntegerField(
        "ID клиента",
        validators=[DataRequired(message="ID клиента - обязательное поле.")],
        render_kw={"hidden": ""},
    )
    comment = TextAreaField("Комментарий", render_kw={"placeholder": "Адрес и комментарий"})
    cart = FieldList(FormField(CartItemForm))
    submit = SubmitField("Отправить заявку на согласование")


################################################################################
# Vendor page
################################################################################


class UploadProductsForm(FlaskForm):
    products = FileField(
        label="Продукты",
        validators=[
            FileRequired("Разрешены только XLSX."),
            FileAllowed(["xlsx"], "Разрешены только XLSX."),
        ],
    )
    submit = SubmitField("Загрузить")


class UploadImagesForm(FlaskForm):
    images = FileField(
        label="Изображения",
        validators=[
            FileRequired("Разрешены только zip архивы."),
            FileAllowed(["zip"], "Разрешены только zip архивы."),
        ],
    )
    submit = SubmitField("Загрузить")


class UploadProductImageForm(FlaskForm):
    image = FileField(
        label="Изображение",
        validators=[
            FileRequired("Разрешены только изображения JPG и PNG!"),
            FileAllowed(["jpg", "png"], "Разрешены только изображения JPG и PNG!"),
        ],
    )
    submit = SubmitField("Загрузить")
