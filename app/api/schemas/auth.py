from app.api.schemas.base import BaseSchema


class TokenPayload(BaseSchema):
    model_config = BaseSchema.model_config.copy()

    sub: str      # user_id
    org_id: str
    exp: int
