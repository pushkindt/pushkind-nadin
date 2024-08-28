from typing import Optional

from pydantic import BaseModel, Field


class ApiProductModel(BaseModel):
    id: int = Field(..., description="ID")
    vendor: str = Field(..., description="Производитель")
    name: str = Field(..., description="Название")
    sku: str = Field(..., description="Артикул")
    price: float = Field(..., description="Цена")
    cat_id: int = Field(..., description="ID категории")
    category: str = Field(..., description="Категория")
    prices: Optional[dict[str, float]] = Field(..., description="Цены")
    image: Optional[str] = Field(..., description="Изображение")
    measurement: Optional[str] = Field(..., description="Единица измерения")
    description: Optional[str] = Field(..., description="Описание")
    options: Optional[dict[str, list[str]]] = Field(..., description="Теги")
    tags: Optional[list[str]] = Field(..., description="Теги")


class ApiOrderItemModel(BaseModel):
    quantity: int = Field(..., description="Количество")
    comment: Optional[str] = Field(..., description="Комментарий")
    product: ApiProductModel = Field(..., description="Товар")
    options: Optional[dict[str, str]] = Field(None, description="Выбранные опции")


class ApiShoppingCartModel(BaseModel):
    items: dict[str, ApiOrderItemModel] = Field(..., description="Товары")
