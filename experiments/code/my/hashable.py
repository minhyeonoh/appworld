
import uuid
from pydantic import BaseModel, Field


class UidAsHash(BaseModel):

  uid: uuid.UUID = Field(default_factory=uuid.uuid4)

  def __hash__(self):
    return hash(self.uid)

  def __eq__(self, other):
    if isinstance(other, UidAsHash):
      return self.uid == other.uid
    return False