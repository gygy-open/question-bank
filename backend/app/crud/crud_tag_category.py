from app.crud.base import CRUDBase
from app.models.tag_category import TagCategory
from app.schemas.tag_category import TagCategoryCreate, TagCategoryUpdate

class CRUDTagCategory(CRUDBase[TagCategory, TagCategoryCreate, TagCategoryUpdate]):
    pass

tag_category = CRUDTagCategory(TagCategory)
