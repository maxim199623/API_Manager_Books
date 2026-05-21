from typing import Any, Type, TypeVar
from sqlalchemy.inspection import inspect as sa_inspect
from pydantic import BaseModel

TModel = TypeVar("TModel")


def build_model_from_schema(
    model_cls: Type[TModel],
    schema_obj: BaseModel,
    extra: dict[str, Any] | None = None,
) -> TModel:
    """
    Создаёт ORM-объект из Pydantic-схемы, беря только те поля,
    которые реально есть в модели.
    """
    data = schema_obj.model_dump(exclude_unset=True)

    mapper = sa_inspect(model_cls)
    allowed_keys = {attr.key for attr in mapper.attrs}

    filtered = {k: v for k, v in data.items() if k in allowed_keys}

    if extra:
        filtered.update(extra)

    return model_cls(**filtered)


def patch_model_from_schema(
    instance: Any,
    schema_obj: BaseModel,
) -> None:
    """
    Частично обновляет ORM-объект из Pydantic-схемы, беря только
    существующие в модели поля и только переданные (exclude_unset).
    """
    data = schema_obj.model_dump(exclude_unset=True)

    mapper = sa_inspect(instance.__class__)
    allowed_keys = {attr.key for attr in mapper.attrs}

    for field, value in data.items():
        if field in allowed_keys:
            setattr(instance, field, value)